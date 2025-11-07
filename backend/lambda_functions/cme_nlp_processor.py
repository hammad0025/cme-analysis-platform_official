"""
CME NLP Processor - Test Intent Detection and Demeanor Analysis
Implements Steps 4 & 7 from the technical documentation
"""

import json
import boto3
import logging
import re
from typing import Dict, Any, List, Tuple, Optional
from decimal import Decimal
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
comprehend_client = boto3.client('comprehend')
bedrock_client = boto3.client('bedrock-runtime')

# Medical test taxonomy for intent detection
TEST_TAXONOMY = {
    'spine': {
        'keywords': ['spine', 'spinal', 'vertebra', 'vertebrae', 'back'],
        'patterns': [
            r'check\s+(?:the\s+)?spine',
            r'examine\s+(?:the\s+)?back',
            r'spinal\s+(?:examination|assessment)'
        ]
    },
    'lumbar_rom': {
        'keywords': ['lumbar', 'lower back', 'range of motion', 'rom', 'flexion', 'extension', 'bend forward', 'bend backward'],
        'patterns': [
            r'(?:lumbar|lower\s+back)\s+range\s+of\s+motion',
            r'(?:forward|backward)\s+(?:flexion|bending)',
            r'rom\s+test'
        ]
    },
    'straight_leg_raise': {
        'keywords': ['straight leg', 'slr', 'leg raise', 'lasegue', 'raise your leg'],
        'patterns': [
            r'straight\s+leg\s+(?:raise|test)',
            r'slr\s+test',
            r'lasegue[\'s]*\s+(?:test|sign)'
        ]
    },
    'waddells_signs': {
        'keywords': ['waddell', 'non-organic', 'behavioral', 'non organic'],
        'patterns': [
            r'waddell[\'s]*\s+(?:signs|test)',
            r'non[-\s]organic\s+(?:signs|findings)'
        ]
    },
    'cervical_rom': {
        'keywords': ['cervical', 'neck', 'rotation', 'lateral flexion', 'turn your head', 'neck movement'],
        'patterns': [
            r'cervical\s+(?:range\s+of\s+motion|rom)',
            r'neck\s+(?:rotation|flexion|movement)',
            r'turn\s+(?:your\s+)?head'
        ]
    },
    'gait': {
        'keywords': ['gait', 'walking', 'ambulation', 'mobility', 'walk', 'heel-to-toe', 'tandem'],
        'patterns': [
            r'gait\s+(?:analysis|assessment|test)',
            r'(?:walk|walking)\s+(?:test|assessment)',
            r'heel[-\s]to[-\s]toe',
            r'tandem\s+(?:walk|gait)'
        ]
    },
    'neurological': {
        'keywords': ['reflex', 'reflexes', 'sensation', 'sensory', 'motor', 'strength', 'muscle strength', 'patellar', 'achilles'],
        'patterns': [
            r'(?:reflex|reflexes)\s+test',
            r'(?:sensory|sensation)\s+(?:test|examination)',
            r'motor\s+(?:strength|function)',
            r'(?:patellar|achilles|bicep|tricep)\s+reflex'
        ]
    },
    'palpation': {
        'keywords': ['palpate', 'palpating', 'feel', 'touch', 'tender', 'tenderness', 'press'],
        'patterns': [
            r'(?:palpate|palpating)\s+(?:the\s+)?(?:spine|back|neck|area)',
            r'check\s+for\s+tenderness',
            r'feel\s+(?:the\s+)?(?:spine|muscles)'
        ]
    },
    'orthopedic': {
        'keywords': ['orthopedic', 'musculoskeletal', 'joint', 'hip', 'knee', 'shoulder', 'ankle'],
        'patterns': [
            r'orthopedic\s+(?:examination|assessment|test)',
            r'(?:hip|knee|shoulder|ankle)\s+(?:test|examination)',
            r'joint\s+(?:mobility|function)'
        ]
    },
    'cognitive': {
        'keywords': ['memory', 'concentration', 'cognitive', 'mental status', 'orientation', 'recall'],
        'patterns': [
            r'cognitive\s+(?:test|assessment|function)',
            r'mental\s+status\s+exam',
            r'memory\s+test',
            r'orientation\s+(?:test|assessment)'
        ]
    }
}

# Demeanor analysis patterns
NEGATIVE_TONE_INDICATORS = [
    'that\'s ridiculous', 'you\'re lying', 'i don\'t believe', 'that\'s impossible',
    'come on', 'really?', 'seriously?', 'you\'re exaggerating', 'that doesn\'t make sense'
]

INTERRUPTION_PATTERNS = [
    r'stop\s+(?:talking|speaking)',
    r'let\s+me\s+(?:speak|talk)',
    r'don\'t\s+(?:interrupt|talk)',
    r'be\s+quiet',
    r'shut\s+up'
]

DISMISSIVE_PATTERNS = [
    r'(?:doesn\'t|does\s+not)\s+matter',
    r'not\s+important',
    r'(?:don\'t|do\s+not)\s+care\s+about',
    r'that\'s\s+(?:irrelevant|not\s+relevant)'
]


class CMENLPProcessor:
    """Process CME transcripts for test intent detection and demeanor analysis"""
    
    def __init__(self):
        self.test_taxonomy = TEST_TAXONOMY
    
    def detect_declared_tests(self, transcript: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Step 4: Test Intent Detection
        Analyze transcript to identify declared medical tests
        
        Args:
            transcript: AWS Transcribe output with speaker labels
            
        Returns:
            List of detected test declarations with timestamps
        """
        declared_tests = []
        
        try:
            # Parse transcript items
            results = transcript.get('results', {})
            items = results.get('items', [])
            speaker_labels = results.get('speaker_labels', {})
            segments = speaker_labels.get('segments', [])
            
            # Process each segment
            for segment in segments:
                speaker = segment.get('speaker_label', 'unknown')
                
                # Only analyze examiner speech (typically speaker_0 or speaker_1)
                # In real implementation, we'd use speaker diarization to identify the examiner
                
                start_time = float(segment.get('start_time', 0))
                end_time = float(segment.get('end_time', 0))
                
                # Get transcript text for this segment
                segment_text = self._get_segment_text(segment, items)
                
                # Detect test declarations
                detected_tests = self._analyze_text_for_tests(segment_text, start_time)
                
                for test in detected_tests:
                    test['speaker'] = speaker
                    test['transcript_text'] = segment_text
                    declared_tests.append(test)
            
            logger.info(f"Detected {len(declared_tests)} test declarations")
            return declared_tests
            
        except Exception as e:
            logger.error(f"Error detecting declared tests: {str(e)}")
            return []
    
    def _get_segment_text(self, segment: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
        """Extract text from a transcript segment"""
        segment_start = float(segment.get('start_time', 0))
        segment_end = float(segment.get('end_time', 0))
        
        words = []
        for item in items:
            if item.get('type') == 'pronunciation':
                item_start = float(item.get('start_time', 0))
                if segment_start <= item_start <= segment_end:
                    content = item.get('alternatives', [{}])[0].get('content', '')
                    words.append(content)
        
        return ' '.join(words)
    
    def _analyze_text_for_tests(self, text: str, timestamp: float) -> List[Dict[str, Any]]:
        """Analyze text segment for test declarations using NLP"""
        detected = []
        text_lower = text.lower()
        
        # Check each test type in taxonomy
        for test_label, test_config in self.test_taxonomy.items():
            confidence = 0.0
            
            # Check keyword matches
            keyword_matches = sum(1 for kw in test_config['keywords'] if kw in text_lower)
            if keyword_matches > 0:
                confidence += 0.3 * min(keyword_matches / len(test_config['keywords']), 1.0)
            
            # Check pattern matches
            pattern_matches = 0
            for pattern in test_config['patterns']:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    pattern_matches += 1
            
            if pattern_matches > 0:
                confidence += 0.7
            
            # Check for declaration phrases
            declaration_phrases = [
                'now we', 'let\'s', 'going to', 'want to', 'need to', 
                'i\'m going to', 'i\'m checking', 'i need', 'we\'re going to'
            ]
            
            has_declaration = any(phrase in text_lower for phrase in declaration_phrases)
            if has_declaration and confidence > 0:
                confidence += 0.2
            
            # If confidence threshold met, add to detected tests
            if confidence >= 0.5:  # Threshold for detection
                detected.append({
                    'label': test_label,
                    'timestamp': timestamp,
                    'confidence': min(confidence, 1.0),
                    'matched_text': text[:200]  # First 200 chars
                })
        
        return detected
    
    def analyze_examiner_demeanor(
        self, 
        transcript: Dict[str, Any],
        examiner_speaker_label: str = 'speaker_0'
    ) -> List[Dict[str, Any]]:
        """
        Step 7: Demeanor & Tone Analysis
        Analyze examiner's tone, politeness, and behavior
        
        Args:
            transcript: AWS Transcribe output
            examiner_speaker_label: Speaker label for the examiner
            
        Returns:
            List of demeanor flags with timestamps
        """
        demeanor_flags = []
        
        try:
            results = transcript.get('results', {})
            speaker_labels = results.get('speaker_labels', {})
            segments = speaker_labels.get('segments', [])
            items = results.get('items', [])
            
            examiner_segments = [s for s in segments if s.get('speaker_label') == examiner_speaker_label]
            
            # Track consecutive examiner utterances (interruptions)
            consecutive_count = 0
            last_speaker = None
            
            for i, segment in enumerate(segments):
                speaker = segment.get('speaker_label')
                start_time = float(segment.get('start_time', 0))
                segment_text = self._get_segment_text(segment, items)
                
                # Count consecutive examiner utterances (interruptions)
                if speaker == examiner_speaker_label:
                    if last_speaker == examiner_speaker_label:
                        consecutive_count += 1
                        if consecutive_count >= 2:  # 3+ consecutive utterances
                            demeanor_flags.append({
                                'flag_type': 'interruption',
                                'timestamp': start_time,
                                'transcript_excerpt': segment_text[:200],
                                'severity': 'medium',
                                'description': f'Examiner spoke {consecutive_count + 1} times consecutively'
                            })
                    else:
                        consecutive_count = 0
                    
                    # Analyze tone and sentiment
                    flags = self._analyze_tone(segment_text, start_time)
                    demeanor_flags.extend(flags)
                
                last_speaker = speaker
            
            # Use AWS Comprehend for sentiment analysis on examiner segments
            examiner_text = ' '.join([
                self._get_segment_text(s, items) for s in examiner_segments[:10]  # First 10 segments
            ])
            
            if examiner_text:
                sentiment_flags = self._analyze_sentiment_comprehend(examiner_text, examiner_segments)
                demeanor_flags.extend(sentiment_flags)
            
            logger.info(f"Detected {len(demeanor_flags)} demeanor flags")
            return demeanor_flags
            
        except Exception as e:
            logger.error(f"Error analyzing demeanor: {str(e)}")
            return []
    
    def _analyze_tone(self, text: str, timestamp: float) -> List[Dict[str, Any]]:
        """Analyze text for negative tone indicators"""
        flags = []
        text_lower = text.lower()
        
        # Check for negative tone indicators
        for indicator in NEGATIVE_TONE_INDICATORS:
            if indicator in text_lower:
                flags.append({
                    'flag_type': 'negative_tone',
                    'timestamp': timestamp,
                    'transcript_excerpt': text[:200],
                    'severity': 'high',
                    'description': f'Negative language detected: "{indicator}"'
                })
        
        # Check for dismissive patterns
        for pattern in DISMISSIVE_PATTERNS:
            if re.search(pattern, text_lower):
                flags.append({
                    'flag_type': 'dismissive',
                    'timestamp': timestamp,
                    'transcript_excerpt': text[:200],
                    'severity': 'medium',
                    'description': 'Dismissive language detected'
                })
        
        # Check for aggressive patterns
        for pattern in INTERRUPTION_PATTERNS:
            if re.search(pattern, text_lower):
                flags.append({
                    'flag_type': 'aggressive',
                    'timestamp': timestamp,
                    'transcript_excerpt': text[:200],
                    'severity': 'high',
                    'description': 'Aggressive or controlling language detected'
                })
        
        return flags
    
    def _analyze_sentiment_comprehend(
        self, 
        text: str, 
        segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Use AWS Comprehend for sentiment analysis"""
        flags = []
        
        try:
            # AWS Comprehend has a 5000 byte limit
            text_sample = text[:5000]
            
            response = comprehend_client.detect_sentiment(
                Text=text_sample,
                LanguageCode='en'
            )
            
            sentiment = response.get('Sentiment')
            sentiment_score = response.get('SentimentScore', {})
            
            # Flag negative sentiment
            if sentiment == 'NEGATIVE' and sentiment_score.get('Negative', 0) > 0.6:
                flags.append({
                    'flag_type': 'negative_sentiment',
                    'timestamp': float(segments[0].get('start_time', 0)) if segments else 0,
                    'transcript_excerpt': text_sample[:200],
                    'severity': 'medium',
                    'description': f'Overall negative sentiment detected (score: {sentiment_score.get("Negative"):.2f})',
                    'sentiment_scores': sentiment_score
                })
            
        except Exception as e:
            logger.error(f"Error in Comprehend sentiment analysis: {str(e)}")
        
        return flags
    
    def extract_medical_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract medical entities using AWS Comprehend Medical"""
        entities = []
        
        try:
            response = comprehend_client.detect_entities_v2(
                Text=text[:20000]  # Comprehend Medical limit
            )
            
            for entity in response.get('Entities', []):
                entities.append({
                    'text': entity.get('Text'),
                    'category': entity.get('Category'),
                    'type': entity.get('Type'),
                    'score': entity.get('Score'),
                    'begin_offset': entity.get('BeginOffset'),
                    'end_offset': entity.get('EndOffset')
                })
            
            return entities
            
        except Exception as e:
            logger.error(f"Error extracting medical entities: {str(e)}")
            return []


def process_transcript_for_cme_analysis(
    session_id: str,
    transcript_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Main processing function for CME transcript analysis
    Combines test intent detection and demeanor analysis
    """
    processor = CMENLPProcessor()
    
    # Step 4: Detect declared tests
    declared_tests = processor.detect_declared_tests(transcript_data)
    
    # Step 7: Analyze demeanor
    demeanor_flags = processor.analyze_examiner_demeanor(transcript_data)
    
    return {
        'session_id': session_id,
        'declared_tests': declared_tests,
        'demeanor_flags': demeanor_flags,
        'processing_timestamp': int(time.time()),
        'status': 'completed'
    }


def enhanced_test_detection_with_ai(transcript_text: str) -> List[Dict[str, Any]]:
    """
    Use Claude/Bedrock for enhanced test detection
    Fallback when pattern matching isn't sufficient
    """
    try:
        prompt = f"""You are analyzing a transcript of a Compulsory Medical Examination (CME). 
Extract all instances where the examiner declares they are performing a specific medical test or examination.

Transcript:
{transcript_text[:4000]}

For each declared test, return JSON with:
- test_type: The type of medical test (e.g., "lumbar_rom", "straight_leg_raise", "gait", "reflex")
- declaration: The exact words the examiner used
- approximate_time: An estimate of when this occurred in the conversation (e.g., "early", "middle", "late")

Return ONLY a JSON array of test declarations, no additional text:
[{{"test_type": "...", "declaration": "...", "approximate_time": "..."}}]"""

        response = bedrock_client.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1500,
                "messages": [{
                    "role": "user",
                    "content": prompt
                }]
            })
        )
        
        response_body = json.loads(response['body'].read())
        ai_result = response_body.get('content', [{}])[0].get('text', '[]')
        
        # Parse AI response
        tests = json.loads(ai_result)
        return tests
        
    except Exception as e:
        logger.error(f"Error in AI-enhanced test detection: {str(e)}")
        return []

