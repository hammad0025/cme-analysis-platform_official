"""
CME NLP Processor - Test Intent Detection and Demeanor Analysis
Implements Steps 4 & 7 from the technical documentation
"""

import json
import boto3
import logging
import os
import re
from typing import Dict, Any, List, Tuple, Optional
from decimal import Decimal
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
comprehend_client = boto3.client('comprehend')
bedrock_client = boto3.client('bedrock-runtime')

DEFAULT_NLP_MODEL_ID = os.environ.get('CME_NLP_MODEL_ID', 'amazon.nova-lite-v1:0')
DEFAULT_NLP_ANTHROPIC_MODEL_ID = os.environ.get(
    'CME_NLP_ANTHROPIC_MODEL_ID',
    'us.anthropic.claude-sonnet-5'
)

# Comprehensive Medical Test Taxonomy for CME/IME Detection
# Based on common physical examination tests in medico-legal contexts
TEST_TAXONOMY = {
    'range_of_motion': {
        'keywords': ['range of motion', 'rom', 'flexion', 'extension', 'limited', 'measured in degrees', 'restricted', 'move', 'bend', 'turn', 'rotate', 'twist', 'flex', 'extend', 'side to side', 'up and down', 'left and right'],
        'patterns': [
            r'range\s+of\s+motion\s+(?:was\s+)?measured',
            r'(?:flexion|extension)\s+(?:were|was)\s+limited',
            r'rom\s+(?:is\s+)?restricted',
            r'limited\s+(?:in\s+)?all\s+planes',
            r'move\s+(?:your|the)\s+(?:neck|back|shoulder|arm|leg|wrist|ankle)',
            r'bend\s+(?:your|the)\s+(?:neck|back|knee|elbow)',
            r'turn\s+(?:your|the)\s+(?:head|neck)',
            r'rotate\s+(?:your|the)',
            r'flex\s+(?:your|the)',
            r'extend\s+(?:your|the)'
        ],
        'category': 'orthopedic',
        'priority': 'high'
    },
    'gait_observation': {
        'keywords': ['gait', 'walk', 'walking', 'ambulation', 'mobility', 'step', 'stride', 'limp', 'limping'],
        'patterns': [
            r'walk\s+(?:for|to|across|back)',
            r'gait\s+(?:is|was)',
            r'walking\s+(?:pattern|abnormal|normal)',
            r'step\s+(?:forward|back|up)',
            r'limp',
            r'stride'
        ],
        'category': 'orthopedic',
        'priority': 'high'
    },
    'manual_muscle_testing': {
        'keywords': ['strength', 'weakness', 'strong', 'weak', 'resistance', 'push', 'pull', 'squeeze', 'grip', 'hold', 'mmt', 'muscle strength'],
        'patterns': [
            r'strength\s+(?:is|was|test)',
            r'(?:push|pull)\s+(?:against|on)',
            r'squeeze\s+(?:my|the)',
            r'grip\s+(?:strength|test)',
            r'resistance',
            r'muscle\s+strength',
            r'\d[/]\d\s+strength'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    'palpation': {
        'keywords': ['palpate', 'palpating', 'feel', 'touch', 'press', 'pressure', 'tender', 'tenderness', 'sore'],
        'patterns': [
            r'palpat(?:e|ing)',
            r'feel\s+(?:for|the)',
            r'touch\s+(?:here|there)',
            r'press\s+(?:on|here)',
            r'tender',
            r'tenderness'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'straight_leg_raise': {
        'keywords': ['straight leg raise', 'slr', 'positive at', 'negative straight', 'lasegue'],
        'patterns': [
            r'straight\s+leg\s+raise\s+(?:was\s+)?positive',
            r'slr\s+(?:positive|negative)',
            r'negative\s+straight[-\s]leg\s+raise'
        ],
        'category': 'orthopedic',
        'priority': 'high'
    },
    'cross_straight_leg_raise': {
        'keywords': ['crossed straight', 'contralateral', 'well leg raise', 'opposite leg'],
        'patterns': [
            r'crossed\s+straight[-\s]leg\s+raise',
            r'contralateral\s+slr',
            r'well\s+leg\s+raise',
            r'positive\s+(?:well\s+leg|contralateral)'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'faber_test': {
        'keywords': ['faber', 'patrick', 'figure-4', 'si joint', 'hip pain'],
        'patterns': [
            r'faber\s+test',
            r'patrick[\'s]*\s+test',
            r'figure[-\s]4\s+position'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'spurlings_test': {
        'keywords': ['spurling', 'foraminal compression', 'radicular pain', 'neck'],
        'patterns': [
            r'spurling[\'s]*\s+(?:test|maneuver)',
            r'foraminal\s+compression',
            r'radicular\s+pain'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'drop_arm_test': {
        'keywords': ['drop arm', 'rotator cuff', 'lower the arm', '90° abduction'],
        'patterns': [
            r'drop\s+arm\s+test',
            r'unable\s+to\s+(?:smoothly\s+)?lower\s+(?:the\s+)?arm',
            r'arm\s+drops?\s+suddenly'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'hawkins_kennedy_test': {
        'keywords': ['hawkins', 'kennedy', 'impingement', 'shoulder pain', 'internally rotate'],
        'patterns': [
            r'hawkins[-\s]kennedy\s+test',
            r'hawkins\s+impingement',
            r'internal(?:ly)?\s+rotat(?:e|ion)'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'neer_test': {
        'keywords': ['neer', 'impingement', 'forward flexion', 'overhead'],
        'patterns': [
            r'neer[\'s]*\s+(?:test|sign)',
            r'neer\s+impingement',
            r'forced\s+forward\s+flexion'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'lachman_test': {
        'keywords': ['lachman', 'acl', 'anterior translation', 'soft endpoint', 'knee'],
        'patterns': [
            r'lachman\s+test',
            r'acl\s+(?:tear|laxity)',
            r'anterior\s+translation',
            r'soft\s+endpoint'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'mcmurray_test': {
        'keywords': ['mcmurray', 'meniscus', 'click', 'knee', 'joint line'],
        'patterns': [
            r'mcmurray[\'s]*\s+test',
            r'meniscal\s+tear',
            r'click\s+(?:in\s+)?(?:the\s+)?knee'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'phalens_test': {
        'keywords': ['phalen', 'carpal tunnel', 'wrist flexion', 'tingling', 'fingers'],
        'patterns': [
            r'phalen[\'s]*\s+(?:test|maneuver)',
            r'carpal\s+tunnel',
            r'wrist\s+flexion',
            r'tingling\s+(?:in\s+)?fingers'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'tinels_sign': {
        'keywords': ['tinel', 'tapping', 'nerve', 'tingling', 'pins and needles'],
        'patterns': [
            r'tinel[\'s]*\s+sign',
            r'tapping\s+over\s+(?:the\s+)?(?:median|ulnar)\s+nerve',
            r'pins\s+and\s+needles'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'trendelenburg_sign': {
        'keywords': ['trendelenburg', 'pelvic drop', 'hip abductor', 'one leg'],
        'patterns': [
            r'trendelenburg\s+sign',
            r'pelvic\s+drop',
            r'standing\s+on\s+one\s+leg'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'deep_tendon_reflexes': {
        'keywords': ['deep tendon', 'dtr', 'reflex', 'patellar', 'achilles', 'biceps', 'triceps', 'brachioradialis', '2+', 'brisk', 'absent', 'knee reflex', 'ankle reflex'],
        'patterns': [
            r'deep\s+tendon\s+reflex(?:es)?',
            r'dtr[s]*',
            r'(?:patellar|achilles|biceps|triceps|brachioradialis)\s+reflex',
            r'reflex(?:es)?\s+(?:at\s+)?(?:knees?|ankles?)',
            r'reflex(?:es)?\s+(?:\d\+|brisk|absent|diminished)',
            r'(?:knee|ankle)\s+reflex'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    'babinski_sign': {
        'keywords': ['babinski', 'plantar response', 'upgoing toe', 'downgoing', 'extensor'],
        'patterns': [
            r'babinski\s+sign',
            r'plantar\s+response',
            r'(?:upgoing|downgoing)\s+toe',
            r'extensor\s+plantar'
        ],
        'category': 'neurological',
        'priority': 'medium'
    },
    'hoffmanns_sign': {
        'keywords': ['hoffmann', 'hoffman', 'flick', 'middle finger', 'thumb flexion', 'cervical'],
        'patterns': [
            r'hoffmann[\'s]*\s+(?:sign|reflex)',
            r'hoffman[\'s]*\s+(?:sign|reflex)',
            r'flick(?:ing)?\s+(?:the\s+)?middle\s+finger',
            r'hoffmann'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    'clonus_test': {
        'keywords': ['clonus', 'ankle', 'sustained', 'beats', 'rhythmic'],
        'patterns': [
            r'clonus\s+(?:present|noted|absent)',
            r'sustained\s+clonus',
            r'beats\s+of\s+clonus'
        ],
        'category': 'neurological',
        'priority': 'medium'
    },
    'romberg_test': {
        'keywords': ['romberg', 'balance', 'eyes closed', 'sway', 'proprioception'],
        'patterns': [
            r'romberg\s+(?:test|sign)',
            r'balance\s+with\s+eyes\s+closed',
            r'increased\s+sway'
        ],
        'category': 'neurological',
        'priority': 'medium'
    },
    'light_touch_sensation': {
        'keywords': ['light touch', 'sensation', 'intact', 'decreased', 'dermatome', 'numbness', 'feel this', 'can you feel', 'feel here'],
        'patterns': [
            r'light\s+touch\s+sensation',
            r'sensation\s+(?:is\s+)?intact',
            r'decreased\s+(?:light\s+)?touch',
            r'any\s+numbness\s+(?:in|here)',
            r'can\s+you\s+feel\s+(?:this|that|here)',
            r'feel\s+(?:this|that|here)',
            r'touch(?:ing)?\s+(?:your|the)\s+(?:thumb|finger|leg|arm)'
        ],
        'category': 'sensory',
        'priority': 'high'
    },
    'pinprick_sensation': {
        'keywords': ['pinprick', 'sharp', 'dull', 'pin sensation', 'discrimination'],
        'patterns': [
            r'pinprick\s+sensation',
            r'sharp[/\s]dull',
            r'pin\s+sensation',
            r'sharp[/\s]dull\s+discrimination'
        ],
        'category': 'sensory',
        'priority': 'high'
    },
    'vibration_sense': {
        'keywords': ['vibration', 'tuning fork', 'vibratory', 'great toe', 'malleolus'],
        'patterns': [
            r'vibration\s+sense',
            r'vibratory\s+sensation',
            r'tuning\s+fork'
        ],
        'category': 'sensory',
        'priority': 'medium'
    },
    'proprioception': {
        'keywords': ['proprioception', 'joint position', 'position sense', 'up or down'],
        'patterns': [
            r'proprioception\s+test',
            r'joint\s+position\s+sense',
            r'position\s+sense'
        ],
        'category': 'sensory',
        'priority': 'medium'
    },
    'gait_observation': {
        'keywords': ['gait', 'antalgic', 'limping', 'walking', 'stride', 'assistive device'],
        'patterns': [
            r'gait\s+(?:was|is)\s+(?:antalgic|normal|abnormal)',
            r'limp(?:ing)?\s+noted',
            r'walking\s+(?:with|without)\s+(?:assistive\s+)?device'
        ],
        'category': 'functional',
        'priority': 'high'
    },
    'heel_walking': {
        'keywords': ['heel walk', 'walk on heels', 'dorsiflexor', 'tibialis anterior'],
        'patterns': [
            r'heel\s+walk(?:ing)?',
            r'walk(?:ing)?\s+on\s+heels',
            r'(?:able|unable)\s+to\s+walk\s+on\s+heels'
        ],
        'category': 'functional',
        'priority': 'high'
    },
    'toe_walking': {
        'keywords': ['toe walk', 'walk on toes', 'plantarflexor', 'calf', 'tiptoes'],
        'patterns': [
            r'toe\s+walk(?:ing)?',
            r'walk(?:ing)?\s+on\s+toes',
            r'(?:able|unable)\s+to\s+walk\s+on\s+toes',
            r'tiptoes'
        ],
        'category': 'functional',
        'priority': 'high'
    },
    'tandem_gait': {
        'keywords': ['tandem', 'heel-to-toe', 'balance', 'straight line'],
        'patterns': [
            r'tandem\s+(?:gait|walk)',
            r'heel[-\s]to[-\s]toe',
            r'walk(?:ing)?\s+(?:in\s+)?(?:a\s+)?straight\s+line'
        ],
        'category': 'functional',
        'priority': 'medium'
    },
    'sit_to_stand': {
        'keywords': ['sit to stand', 'rise from', 'seated position', 'chair', 'arm support'],
        'patterns': [
            r'sit[-\s]to[-\s]stand',
            r'ris(?:e|ing)\s+from\s+(?:seated|chair)',
            r'(?:needs|uses)\s+arm\s+support'
        ],
        'category': 'functional',
        'priority': 'medium'
    },
    'stair_climb': {
        'keywords': ['stair', 'climb', 'ascend', 'descend', 'step', 'railing'],
        'patterns': [
            r'stair\s+climb',
            r'ascend(?:s|ing)?\s+(?:and\s+)?descend',
            r'step\s+up\s+and\s+down',
            r'uses?\s+railing'
        ],
        'category': 'functional',
        'priority': 'medium'
    },
    'squat_and_rise': {
        'keywords': ['squat', 'rise', 'full squat', 'knee flexion', 'difficulty'],
        'patterns': [
            r'squat\s+(?:and\s+)?rise',
            r'full\s+squat',
            r'half[-\s]squat',
            r'difficulty\s+squatting'
        ],
        'category': 'functional',
        'priority': 'medium'
    },
    'axial_loading': {
        'keywords': ['axial loading', 'axial compression', 'downward pressure', 'skull', 'non-organic'],
        'patterns': [
            r'axial\s+loading',
            r'axial\s+compression',
            r'downward\s+pressure\s+on\s+(?:the\s+)?head',
            r'non[-\s]organic\s+finding'
        ],
        'category': 'simulation',
        'priority': 'high'
    },
    'simulated_rotation': {
        'keywords': ['simulated rotation', 'en bloc', 'trunk rotation', 'shoulders and pelvis', 'non-organic'],
        'patterns': [
            r'simulated\s+rotation',
            r'en\s+bloc\s+(?:rotation|trunk)',
            r'rotating?\s+shoulders\s+and\s+pelvis'
        ],
        'category': 'simulation',
        'priority': 'high'
    },
    'superficial_tenderness': {
        'keywords': ['superficial tenderness', 'light touch', 'widespread', 'non-anatomic'],
        'patterns': [
            r'superficial\s+tenderness',
            r'widespread\s+tenderness',
            r'light\s+touch\s+(?:causes|elicits)\s+pain'
        ],
        'category': 'simulation',
        'priority': 'high'
    },
    'non_anatomic_tenderness': {
        'keywords': ['non-anatomic', 'diffuse', 'broad area', 'not localized'],
        'patterns': [
            r'non[-\s]anatomic\s+tenderness',
            r'diffuse\s+(?:pain|tenderness)',
            r'broad\s+area'
        ],
        'category': 'simulation',
        'priority': 'high'
    },
    'distracted_slr': {
        'keywords': ['distracted', 'flip test', 'inconsistent', 'seated', 'supine slr'],
        'patterns': [
            r'distracted\s+(?:straight\s+leg|slr)',
            r'flip\s+test',
            r'inconsistent\s+(?:straight\s+leg|slr)',
            r'seated\s+(?:vs\s+)?supine'
        ],
        'category': 'simulation',
        'priority': 'high'
    },
    'give_way_weakness': {
        'keywords': ['give-way', 'giveway', 'cogwheel', 'inconsistent effort', 'regional weakness'],
        'patterns': [
            r'give[-\s]way\s+weakness',
            r'cogwheel\s+weakness',
            r'inconsistent\s+effort',
            r'regional\s+weakness'
        ],
        'category': 'simulation',
        'priority': 'high'
    },
    'hoovers_test': {
        'keywords': ['hoover', 'downward pressure', 'opposite heel', 'lack of effort'],
        'patterns': [
            r'hoover[\'s]*\s+(?:test|sign)',
            r'downward\s+pressure\s+(?:from\s+)?opposite',
            r'lack\s+of\s+effort'
        ],
        'category': 'simulation',
        'priority': 'medium'
    },
    'manual_muscle_testing': {
        'keywords': ['manual muscle', 'mmt', 'strength', '5/5', '4/5', 'muscle groups', 'upper extremity strength', 'lower extremity strength', 'push against', 'pull against', 'resist'],
        'patterns': [
            r'manual\s+muscle\s+test(?:ing)?',
            r'mmt',
            r'strength\s+(?:is\s+)?\d[/]\d',
            r'\d[/]\d\s+(?:strength|weakness)',
            r'(?:upper|lower)\s+extremity\s+strength',
            r'strength\s+(?:test|testing)',
            r'push\s+(?:against|on)',
            r'pull\s+(?:against|on)',
            r'resist\s+(?:me|this)'
        ],
        'category': 'MMT',
        'priority': 'high'
    },
    # Vital Signs & Basic Measurements
    'blood_pressure': {
        'keywords': ['blood pressure', 'bp', 'systolic', 'diastolic', 'cuff', 'mmhg'],
        'patterns': [
            r'blood\s+pressure\s+(?:is|was|measured)',
            r'\d+/\d+\s+(?:blood\s+)?pressure',
            r'(?:systolic|diastolic)\s+pressure',
            r'manual\s+cuff'
        ],
        'category': 'vital_signs',
        'priority': 'high'
    },
    'pulse_check': {
        'keywords': ['pulse', 'heart rate', 'hr', 'beats per minute', 'bpm', 'radial pulse'],
        'patterns': [
            r'pulse\s+(?:is|was|checked|measured)',
            r'heart\s+rate\s+(?:is|was)',
            r'\d+\s+(?:bpm|beats)',
            r'radial\s+pulse'
        ],
        'category': 'vital_signs',
        'priority': 'high'
    },
    'height_weight': {
        'keywords': ['height', 'weight', 'ht', 'wt', 'bmi', 'body mass index'],
        'patterns': [
            r'(?:height|weight)\s+(?:is|was)\s+(?:measured|reported|checked|taken)',
            r'(?:measured|reported|taken)\s+(?:height|weight)',
            r'bmi\s+(?:is|was|calculated)',
            r'body\s+mass\s+index',
            r'weigh\s+(?:you|patient|them)',
            r'measure\s+(?:your|their)\s+(?:height|weight)'
        ],
        'category': 'vital_signs',
        'priority': 'medium'
    },
    # Inspection & Visual Examination
    'visual_inspection': {
        'keywords': ['inspect', 'inspection', 'visual', 'look at', 'examine', 'observe', 'scar', 'deformity', 'asymmetry'],
        'patterns': [
            r'inspect(?:ion|ed)?\s+(?:the|of)',
            r'visual\s+(?:inspection|examination)',
            r'look(?:ing)?\s+(?:at|for)',
            r'scar(?:s)?\s+(?:present|noted|observed)',
            r'deformity\s+(?:present|noted)'
        ],
        'category': 'inspection',
        'priority': 'high'
    },
    # Cervical ROM Specific
    'cervical_side_bending': {
        'keywords': ['cervical side bending', 'neck side bending', 'lateral flexion', 'neck tilt'],
        'patterns': [
            r'cervical\s+side\s+bending',
            r'neck\s+side\s+bending',
            r'lateral\s+flexion\s+(?:of\s+)?(?:the\s+)?neck',
            r'(?:tilt|bend)\s+(?:your|the)\s+neck\s+(?:left|right)'
        ],
        'category': 'orthopedic',
        'priority': 'high'
    },
    # Shoulder ROM Specific
    'shoulder_adduction': {
        'keywords': ['shoulder adduction', 'adduct', 'bring arm across'],
        'patterns': [
            r'shoulder\s+adduction',
            r'adduct(?:ion)?\s+(?:the\s+)?shoulder',
            r'bring\s+(?:your|the)\s+arm\s+across'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'shoulder_flexion': {
        'keywords': ['shoulder flexion', 'forward flexion', 'raise arm forward'],
        'patterns': [
            r'shoulder\s+flexion',
            r'forward\s+flexion\s+(?:of\s+)?(?:the\s+)?shoulder',
            r'raise\s+(?:your|the)\s+arm\s+forward'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'shoulder_extension': {
        'keywords': ['shoulder extension', 'extend shoulder', 'arm back'],
        'patterns': [
            r'shoulder\s+extension',
            r'extend\s+(?:your|the)\s+shoulder',
            r'bring\s+(?:your|the)\s+arm\s+back'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'shoulder_external_rotation': {
        'keywords': ['shoulder external rotation', 'external rotation', 'rotate arm outward'],
        'patterns': [
            r'shoulder\s+external\s+rotation',
            r'external\s+rotation\s+(?:of\s+)?(?:the\s+)?shoulder',
            r'rotate\s+(?:your|the)\s+arm\s+outward'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    # Elbow ROM
    'elbow_rom': {
        'keywords': ['elbow range of motion', 'elbow flexion', 'elbow extension', 'elbow rom'],
        'patterns': [
            r'elbow\s+(?:range\s+of\s+motion|rom)',
            r'elbow\s+(?:flexion|extension)',
            r'bend\s+(?:your|the)\s+elbow',
            r'straighten\s+(?:your|the)\s+elbow'
        ],
        'category': 'orthopedic',
        'priority': 'high'
    },
    'elbow_supination_pronation': {
        'keywords': ['supination', 'pronation', 'palm up', 'palm down', 'turn hand'],
        'patterns': [
            r'(?:supination|pronation)',
            r'turn\s+(?:your|the)\s+hand\s+(?:up|down)',
            r'palm\s+(?:up|down)'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    # Wrist ROM
    'wrist_rom': {
        'keywords': ['wrist flexion', 'wrist extension', 'wrist rom', 'wrist eversion', 'wrist inversion'],
        'patterns': [
            r'wrist\s+(?:range\s+of\s+motion|rom|flexion|extension)',
            r'wrist\s+(?:eversion|inversion)',
            r'bend\s+(?:your|the)\s+wrist'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    # Hip ROM
    'hip_extension': {
        'keywords': ['hip extension', 'extend hip', 'leg back'],
        'patterns': [
            r'hip\s+extension',
            r'extend\s+(?:your|the)\s+hip',
            r'bring\s+(?:your|the)\s+leg\s+back'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'hip_abduction': {
        'keywords': ['hip abduction', 'abduct hip', 'leg out', 'spread legs'],
        'patterns': [
            r'hip\s+abduction',
            r'abduct\s+(?:your|the)\s+hip',
            r'bring\s+(?:your|the)\s+leg\s+out'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'hip_adduction': {
        'keywords': ['hip adduction', 'adduct hip', 'leg in', 'bring legs together'],
        'patterns': [
            r'hip\s+adduction',
            r'adduct\s+(?:your|the)\s+hip',
            r'bring\s+(?:your|the)\s+legs?\s+together'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'hip_internal_rotation': {
        'keywords': ['hip internal rotation', 'rotate hip inward'],
        'patterns': [
            r'hip\s+internal\s+rotation',
            r'internal\s+rotation\s+(?:of\s+)?(?:the\s+)?hip',
            r'rotate\s+(?:your|the)\s+hip\s+inward'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'hip_external_rotation': {
        'keywords': ['hip external rotation', 'rotate hip outward'],
        'patterns': [
            r'hip\s+external\s+rotation',
            r'external\s+rotation\s+(?:of\s+)?(?:the\s+)?hip',
            r'rotate\s+(?:your|the)\s+hip\s+outward'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    # Ankle ROM
    'ankle_eversion': {
        'keywords': ['ankle eversion', 'evert ankle', 'turn foot out'],
        'patterns': [
            r'ankle\s+eversion',
            r'evert\s+(?:your|the)\s+ankle',
            r'turn\s+(?:your|the)\s+foot\s+out'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    'ankle_inversion': {
        'keywords': ['ankle inversion', 'invert ankle', 'turn foot in'],
        'patterns': [
            r'ankle\s+inversion',
            r'invert\s+(?:your|the)\s+ankle',
            r'turn\s+(?:your|the)\s+foot\s+in'
        ],
        'category': 'orthopedic',
        'priority': 'medium'
    },
    # Lumbar ROM Specific
    'lumbar_rotation': {
        'keywords': ['lumbar rotation', 'back rotation', 'rotate trunk', 'twist'],
        'patterns': [
            r'lumbar\s+rotation',
            r'back\s+rotation',
            r'rotate\s+(?:your|the)\s+trunk',
            r'twist\s+(?:your|the)\s+back'
        ],
        'category': 'orthopedic',
        'priority': 'high'
    },
    # Cranial Nerve Tests
    'cranial_nerve_examination': {
        'keywords': ['cranial nerve', 'cn', 'cranial nerves', 'cn i', 'cn ii', 'cn iii', 'cn iv', 'cn v', 'cn vi', 'cn vii', 'cn viii', 'cn ix', 'cn x', 'cn xi', 'cn xii'],
        'patterns': [
            r'cranial\s+nerve(?:s)?\s+(?:examination|test|testing)',
            r'cn\s+[ivx]+',
            r'(?:olfactory|optic|oculomotor|trochlear|trigeminal|abducens|facial|vestibulocochlear|glossopharyngeal|vagus|accessory|hypoglossal)\s+nerve'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    'olfactory_test': {
        'keywords': ['smell', 'olfactory', 'coffee', 'odor', 'nostril'],
        'patterns': [
            r'smell\s+(?:test|testing)',
            r'olfactory\s+(?:test|function)',
            r'identify\s+(?:the\s+)?(?:smell|odor)',
            r'smell\s+(?:in\s+)?(?:each|both)\s+nostril'
        ],
        'category': 'neurological',
        'priority': 'medium'
    },
    'visual_acuity': {
        'keywords': ['visual acuity', 'vision', 'eye chart', 'snellen', '20/20', 'read letters'],
        'patterns': [
            r'visual\s+acuity',
            r'read\s+(?:the\s+)?(?:letters|chart)',
            r'eye\s+chart',
            r'\d+/\d+\s+vision'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    'visual_fields': {
        'keywords': ['visual fields', 'peripheral vision', 'field of vision', 'confrontation'],
        'patterns': [
            r'visual\s+fields?',
            r'peripheral\s+vision',
            r'field\s+(?:of\s+)?vision',
            r'confrontation\s+(?:test|testing)'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    'pupil_reaction': {
        'keywords': ['pupil', 'pupillary', 'reaction to light', 'accommodation', 'pupils equal'],
        'patterns': [
            r'pupil(?:s|ary)?\s+(?:reaction|response)',
            r'reaction\s+to\s+light',
            r'pupils?\s+(?:equal|round|reactive)',
            r'accommodation'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    'eye_movements': {
        'keywords': ['eye movements', 'extraocular', 'eom', 'follow finger', 'look up down left right'],
        'patterns': [
            r'eye\s+movements?',
            r'extraocular\s+movements?',
            r'eom\s+(?:intact|full)',
            r'follow\s+(?:my|the)\s+finger',
            r'look\s+(?:up|down|left|right)'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    'facial_nerve_test': {
        'keywords': ['facial nerve', 'raise eyebrows', 'close eyes', 'puff cheeks', 'pursed lips'],
        'patterns': [
            r'facial\s+nerve',
            r'raise\s+(?:your|the)\s+eyebrows?',
            r'close\s+(?:your|the)\s+eyes?',
            r'puff\s+(?:out\s+)?(?:your|the)\s+cheeks?',
            r'pursed?\s+lips?'
        ],
        'category': 'neurological',
        'priority': 'medium'
    },
    'hearing_test': {
        'keywords': ['hearing', 'whisper test', 'rinne', 'weber', 'tuning fork', '512 hz'],
        'patterns': [
            r'hearing\s+(?:test|testing)',
            r'whisper(?:ed)?\s+(?:test|word|number)',
            r'rinne[\'s]*\s+test',
            r'weber[\'s]*\s+test',
            r'tuning\s+fork'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    'gag_reflex': {
        'keywords': ['gag reflex', 'say ahhh', 'soft palate', 'uvula'],
        'patterns': [
            r'gag\s+reflex',
            r'say\s+ahhh?',
            r'soft\s+palate',
            r'uvula'
        ],
        'category': 'neurological',
        'priority': 'medium'
    },
    'shoulder_shrug': {
        'keywords': ['shoulder shrug', 'shrug shoulders', 'accessory nerve'],
        'patterns': [
            r'shoulder\s+shrug',
            r'shrug\s+(?:your|the)\s+shoulders?',
            r'accessory\s+nerve'
        ],
        'category': 'neurological',
        'priority': 'medium'
    },
    'tongue_examination': {
        'keywords': ['tongue', 'hypoglossal', 'protrude tongue', 'tongue movements', 'fasciculations'],
        'patterns': [
            r'tongue\s+(?:examination|test|movements?)',
            r'hypoglossal\s+nerve',
            r'protrude\s+(?:your|the)\s+tongue',
            r'stick\s+out\s+(?:your|the)\s+tongue',
            r'fasciculations?'
        ],
        'category': 'neurological',
        'priority': 'medium'
    },
    # Mental Status & Cognitive Testing
    'moca_test': {
        'keywords': ['moca', 'montreal cognitive assessment', 'cognitive assessment'],
        'patterns': [
            r'moca',
            r'montreal\s+cognitive\s+assessment',
            r'cognitive\s+assessment'
        ],
        'category': 'cognitive',
        'priority': 'high'
    },
    'higher_cortical_functions': {
        'keywords': ['higher cortical', 'hcf', 'language', 'memory', 'executive function', 'attention', 'concentration', 'calculation', 'praxis'],
        'patterns': [
            r'higher\s+cortical\s+functions?',
            r'hcf',
            r'language\s+(?:skills|comprehension|expression)',
            r'memory\s+(?:test|testing|recall)',
            r'executive\s+functions?',
            r'attention\s+(?:and\s+)?concentration',
            r'calculation\s+(?:skills|test)',
            r'praxis'
        ],
        'category': 'cognitive',
        'priority': 'high'
    },
    'memory_testing': {
        'keywords': ['memory', 'recall', 'remember', '5 objects', 'delayed recall', 'immediate recall'],
        'patterns': [
            r'memory\s+(?:test|testing)',
            r'recall\s+(?:test|testing)',
            r'remember\s+(?:these|the)',
            r'\d+\s+objects?\s+to\s+remember',
            r'delayed\s+recall',
            r'immediate\s+recall'
        ],
        'category': 'cognitive',
        'priority': 'high'
    },
    # Additional Sensory Tests
    'two_point_discrimination': {
        'keywords': ['two point', '2 point', 'discrimination', 'two-point'],
        'patterns': [
            r'two[-\s]point\s+discrimination',
            r'2[-\s]point\s+discrimination',
            r'discrimination\s+test'
        ],
        'category': 'sensory',
        'priority': 'medium'
    },
    'temperature_sensation': {
        'keywords': ['temperature', 'hot', 'cold', 'warm', 'cool', 'thermal'],
        'patterns': [
            r'temperature\s+sensation',
            r'(?:hot|cold|warm|cool)\s+sensation',
            r'thermal\s+sensation',
            r'feel\s+(?:hot|cold|warm|cool)'
        ],
        'category': 'sensory',
        'priority': 'medium'
    },
    'graphesthesia': {
        'keywords': ['graphesthesia', 'number writing', 'draw on palm', 'identify number'],
        'patterns': [
            r'graphesthesia',
            r'number\s+writing',
            r'draw\s+(?:a\s+)?number\s+on',
            r'identify\s+(?:the\s+)?number'
        ],
        'category': 'sensory',
        'priority': 'medium'
    },
    'stereognosis': {
        'keywords': ['stereognosis', 'identify object', 'feel object', 'object recognition'],
        'patterns': [
            r'stereognosis',
            r'identify\s+(?:the\s+)?object',
            r'feel\s+(?:the\s+)?object',
            r'object\s+recognition'
        ],
        'category': 'sensory',
        'priority': 'medium'
    },
    # Additional Reflexes
    'brachioradialis_reflex': {
        'keywords': ['brachioradialis', 'brachioradialis reflex', 'radial reflex'],
        'patterns': [
            r'brachioradialis\s+reflex',
            r'radial\s+reflex',
            r'brachioradialis'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    # Additional Tests
    'lhermittes_sign': {
        'keywords': ['lhermitte', 'electric shock', 'neck flexion', 'shock down spine'],
        'patterns': [
            r'lhermitte[\'s]*\s+(?:sign|test)',
            r'electric\s+shock',
            r'shock\s+down\s+(?:the\s+)?spine',
            r'neck\s+flexion\s+(?:causes|causing)'
        ],
        'category': 'neurological',
        'priority': 'medium'
    },
    'coordination_testing': {
        'keywords': ['coordination', 'finger to nose', 'heel to shin', 'rapid alternating', 'dysdiadochokinesia'],
        'patterns': [
            r'coordination\s+(?:test|testing)',
            r'finger\s+to\s+nose',
            r'heel\s+to\s+shin',
            r'rapid\s+alternating',
            r'dysdiadochokinesia'
        ],
        'category': 'neurological',
        'priority': 'high'
    },
    # Pulse Checks
    'dorsalis_pedis_pulse': {
        'keywords': ['dorsalis pedis', 'dp pulse', 'foot pulse', 'top of foot'],
        'patterns': [
            r'dorsalis\s+pedis\s+pulse',
            r'dp\s+pulse',
            r'pulse\s+(?:on|at)\s+(?:the\s+)?(?:top\s+of\s+)?(?:the\s+)?foot'
        ],
        'category': 'vascular',
        'priority': 'medium'
    },
    'posterior_tibial_pulse': {
        'keywords': ['posterior tibial', 'pt pulse', 'ankle pulse', 'behind ankle'],
        'patterns': [
            r'posterior\s+tibial\s+pulse',
            r'pt\s+pulse',
            r'pulse\s+(?:on|at|behind)\s+(?:the\s+)?ankle'
        ],
        'category': 'vascular',
        'priority': 'medium'
    },
    'radial_pulse': {
        'keywords': ['radial pulse', 'wrist pulse', 'pulse at wrist'],
        'patterns': [
            r'radial\s+pulse',
            r'pulse\s+(?:at|on)\s+(?:the\s+)?wrist'
        ],
        'category': 'vascular',
        'priority': 'medium'
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
            
            # Process each segment - FILTER TO EXAMINER ONLY
            examiner_speakers = set()
            # Identify examiner (usually speaks more and gives commands)
            speaker_counts = {}
            for segment in segments:
                speaker = segment.get('speaker_label', 'unknown')
                speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1
            
            # Examiner is usually the one who speaks most (or spk_1/spk_0)
            if len(speaker_counts) > 1:
                # Find speaker with most segments (likely examiner)
                examiner_speaker = max(speaker_counts.items(), key=lambda x: x[1])[0]
                examiner_speakers.add(examiner_speaker)
                # Also check common patterns
                if 'spk_1' in speaker_counts:
                    examiner_speakers.add('spk_1')
                if 'spk_0' in speaker_counts:
                    examiner_speakers.add('spk_0')
            else:
                # Only one speaker, assume it's examiner
                examiner_speakers = set(speaker_counts.keys())
            
            logger.info(f"Identified examiner speakers: {examiner_speakers}")
            
            for segment in segments:
                speaker = segment.get('speaker_label', 'unknown')
                
                # ONLY analyze examiner speech
                if speaker not in examiner_speakers:
                    continue
                
                start_time = float(segment.get('start_time', 0))
                end_time = float(segment.get('end_time', 0))
                
                # Get transcript text for this segment
                segment_text = self._get_segment_text(segment, items)
                
                # Skip very short segments (likely just "um", "uh", etc.)
                if len(segment_text.split()) < 3:
                    continue
                
                # Detect test declarations
                detected_tests = self._analyze_text_for_tests(segment_text, start_time)
                
                for test in detected_tests:
                    test['speaker'] = speaker
                    test['transcript_text'] = segment_text
                    declared_tests.append(test)
            
            # DEDUPLICATE - Remove tests that are too close together (same test, different segments)
            # Group by test type and timestamp proximity
            if len(declared_tests) > 0:
                deduplicated = []
                seen_tests = {}  # test_type -> list of timestamps
                
                for test in sorted(declared_tests, key=lambda x: float(x.get('timestamp', 0))):
                    test_type = test.get('label', 'unknown')
                    timestamp = float(test.get('timestamp', 0))
                    
                    # DEDUPLICATE: Remove same test type within 30 seconds
                    # Dr. Hunter identified 27 distinct tests - deduplicate same test mentions
                    is_duplicate = False
                    
                    if test_type in seen_tests:
                        for prev_timestamp in seen_tests[test_type]:
                            if abs(timestamp - prev_timestamp) < 30:  # Same test within 30s = duplicate
                                is_duplicate = True
                                break
                    
                    if not is_duplicate:
                        if test_type not in seen_tests:
                            seen_tests[test_type] = []
                        seen_tests[test_type].append(timestamp)
                        deduplicated.append(test)
                
                declared_tests = deduplicated
                logger.info(f"After deduplication: {len(declared_tests)} unique tests")
            
            # ALWAYS try AI-enhanced detection to catch missed tests
            # Use it as a supplement, not just fallback
            logger.info(f"Pattern matching found {len(declared_tests)} tests, running AI enhancement...")
            try:
                # Get examiner-only transcript text for AI analysis
                examiner_text_parts = []
                for segment in segments:
                    speaker = segment.get('speaker_label', 'unknown')
                    if speaker in examiner_speakers:
                        segment_text = self._get_segment_text(segment, items)
                        if len(segment_text.split()) >= 3:  # Skip very short segments
                            examiner_text_parts.append(segment_text)
                
                examiner_text = ' '.join(examiner_text_parts)
                
                # Use AI to detect tests from examiner speech while keeping
                # each model request bounded for latency and cost.
                max_chunk_size = 20000  # Larger chunks for better context
                ai_tests = []
                
                # Process in chunks if transcript is very long
                if len(examiner_text) > max_chunk_size:
                    logger.info(f"Processing {len(examiner_text)} chars in chunks")
                    chunks = [examiner_text[i:i+max_chunk_size] for i in range(0, len(examiner_text), max_chunk_size)]
                    for i, chunk in enumerate(chunks):
                        logger.info(f"Processing chunk {i+1}/{len(chunks)}")
                        chunk_tests = enhanced_test_detection_with_ai(chunk)
                        ai_tests.extend(chunk_tests)
                else:
                    ai_tests = enhanced_test_detection_with_ai(examiner_text)
                
                # Get existing timestamps to avoid duplicates
                existing_timestamps = {float(t.get('timestamp', 0)) for t in declared_tests}
                
                for ai_test in ai_tests:
                    # Map AI test types to our taxonomy
                    test_type = ai_test.get('test_type', 'unknown')
                    # Use approximate time to find timestamp
                    approx_time = ai_test.get('approximate_time', 'middle')
                    # Estimate timestamp based on position in examiner segments
                    examiner_segments_list = [s for s in segments if s.get('speaker_label') in examiner_speakers]
                    total_examiner_segments = len(examiner_segments_list)
                    
                    if approx_time == 'early':
                        est_timestamp = examiner_segments_list[min(10, total_examiner_segments-1)].get('start_time', 0) if examiner_segments_list else 0
                    elif approx_time == 'late':
                        est_timestamp = examiner_segments_list[max(0, total_examiner_segments-10)].get('start_time', 0) if examiner_segments_list else 0
                    else:
                        est_timestamp = examiner_segments_list[total_examiner_segments//2].get('start_time', 0) if examiner_segments_list else 0
                    
                    # Skip if we already have a test at this timestamp (within 5 seconds)
                    if any(abs(float(t) - float(est_timestamp)) < 5 for t in existing_timestamps):
                        continue
                    
                    from decimal import Decimal
                    declared_tests.append({
                        'label': test_type,
                        'timestamp': Decimal(str(float(est_timestamp))),
                        'confidence': Decimal('0.75'),  # Higher confidence for AI-detected
                        'matched_text': ai_test.get('declaration', '')[:200],
                        'speaker': list(examiner_speakers)[0] if examiner_speakers else 'examiner',
                        'transcript_text': ai_test.get('declaration', ''),
                        'ai_detected': True
                    })
                    existing_timestamps.add(float(est_timestamp))
                
                logger.info(f"AI detection found {len(ai_tests)} additional tests")
            except Exception as ai_error:
                logger.warning(f"AI-enhanced detection failed: {str(ai_error)}")
                import traceback
                logger.warning(traceback.format_exc())
            
            logger.info(f"Detected {len(declared_tests)} test declarations total")
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
            
            # Check keyword matches - BALANCED MODE
            keyword_matches = sum(1 for kw in test_config['keywords'] if kw in text_lower)
            if keyword_matches > 0:
                # Base confidence from keyword matches
                if keyword_matches >= 2:
                    confidence += 0.6  # Multiple keywords = stronger signal
                else:
                    confidence += 0.4  # Single keyword = moderate signal
            
            # Check pattern matches (more specific = higher confidence)
            pattern_matches = 0
            for pattern in test_config['patterns']:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    pattern_matches += 1
            
            if pattern_matches > 0:
                confidence += 0.7  # Pattern match = strong signal
            
            # Check for declaration phrases - MAXIMUM EXPANSION (catch everything)
            declaration_phrases = [
                'now we', 'let\'s', 'going to', 'want to', 'need to', 
                'i\'m going to', 'i\'m checking', 'i need', 'we\'re going to',
                'let me', 'i\'ll', 'i will', 'can you', 'show me', 'move your',
                'test your', 'check your', 'examine your', 'assess', 'evaluate',
                'i want', 'i\'d like', 'try to', 'see if', 'tell me if',
                'does it', 'does that', 'how does', 'how much', 'how far',
                'i\'m going', 'we\'ll', 'we will', 'i\'m testing', 'i\'m examining',
                'let\'s check', 'let\'s see', 'let\'s test', 'let\'s examine',
                'i\'m looking', 'i\'m feeling', 'i\'m checking', 'i notice',
                'i see', 'i observe', 'i feel', 'i can see', 'i can feel'
            ]
            
            # Also check for imperative commands (common in exams) - EXPANDED
            imperative_patterns = [
                r'\b(move|bend|turn|raise|lift|lower|flex|extend|rotate|twist|tilt|lean)\s+(?:your|the|your head|your neck|your back|your arm|your leg|your knee|your shoulder)',
                r'\b(show|demonstrate|try|attempt|do)\s+(?:me|to|this|that)',
                r'\b(stand|sit|walk|step|squeeze|grip|hold|push|pull|press)\s+(?:up|down|on|here|there|against|my|the)',
                r'\b(look|turn|face|point)\s+(?:at|to|left|right|up|down)',
                r'\b(close|open|shut)\s+(?:your|eyes)',
                r'\b(follow|watch|track)\s+(?:my|the|this)',
                r'\b(touch|reach|grab|grasp)\s+(?:your|the|my)',
                r'\b(straighten|bend|flex|extend)\s+(?:your|the)',
                r'\b(raise|lift|lower|drop)\s+(?:your|the)',
                r'\b(spread|separate|bring|together)\s+(?:your|the)'
            ]
            
            has_declaration = any(phrase in text_lower for phrase in declaration_phrases)
            has_imperative = any(re.search(pattern, text_lower) for pattern in imperative_patterns)
            
            if has_declaration and confidence > 0:
                confidence += 0.3  # Declaration bonus
            elif has_imperative and confidence > 0:
                confidence += 0.25  # Imperative bonus
            
            # STRICT DETECTION MODE - require strong evidence
            # Require evidence that this is actually a test, not casual conversation
            has_strong_match = keyword_matches >= 2 or pattern_matches > 0
            has_declaration_context = has_declaration or has_imperative
            
            # BALANCED DETECTION - catch real tests, filter casual mentions
            # MAXIMUM MENTION DETECTION - catch ALL test claims/mentions from audio
            # Goal: Detect every test the doctor CLAIMS/MENTIONS (video will validate actual performance)
            # Detection rules (aggressive but smart):
            # 1. Pattern match = definitely mentioned
            # 2. Keyword + declaration/imperative = test claim
            # 3. Multiple keywords = test mentioned
            # 4. Single keyword + declaration context = test claim
            
            should_detect = False
            if pattern_matches > 0:
                should_detect = True  # Pattern match = definitely mentioned
            elif keyword_matches >= 1 and (has_declaration_context or has_imperative):
                should_detect = True  # Keyword + context = test claim
            elif keyword_matches >= 2:
                should_detect = True  # Multiple keywords = mentioned
            elif keyword_matches >= 1 and confidence >= 0.3:
                should_detect = True  # Single keyword with some confidence = mentioned
            
            if should_detect:
                detected.append({
                    'label': test_label,
                    'timestamp': timestamp,
                    'confidence': min(confidence, 1.0),
                    'matched_text': text[:200]  # First 200 chars
                })
        
        # Return only the BEST match (highest confidence) to avoid duplicate/misclassified tests
        if detected:
            # Sort by confidence descending
            detected.sort(key=lambda x: x['confidence'], reverse=True)
            # Return only the top match
            return [detected[0]]
        
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
    **NOW WITH DYNAMODB PERSISTENCE**
    """
    import os
    import boto3
    
    dynamodb = boto3.resource('dynamodb')
    steps_table = dynamodb.Table(os.environ.get('CME_STEPS_TABLE', 'cme-declared-steps'))
    demeanor_table = dynamodb.Table(os.environ.get('CME_DEMEANOR_TABLE', 'cme-demeanor-flags'))
    sessions_table = dynamodb.Table(os.environ.get('CME_SESSIONS_TABLE', 'cme-sessions'))
    
    processor = CMENLPProcessor()
    
    # Step 4: Detect declared tests
    declared_tests = processor.detect_declared_tests(transcript_data)
    
    # *** PERSIST DECLARED TESTS TO DYNAMODB ***
    from decimal import Decimal
    persisted_step_ids = []
    for test in declared_tests:
        step_id = f"step_{int(time.time())}_{len(persisted_step_ids)}"
        
        # *** CRITICAL: Add declared_step_id to test object for video processor ***
        test['declared_step_id'] = step_id
        
        # Convert timestamp and confidence to Decimal for DynamoDB
        timestamp_val = test.get('timestamp', 0)
        if isinstance(timestamp_val, float):
            timestamp_val = Decimal(str(timestamp_val))
        elif not isinstance(timestamp_val, Decimal):
            timestamp_val = Decimal(str(float(timestamp_val)))
        
        confidence_val = test.get('confidence', 0.0)
        if isinstance(confidence_val, float):
            confidence_val = Decimal(str(confidence_val))
        elif not isinstance(confidence_val, Decimal):
            confidence_val = Decimal(str(float(confidence_val)))
        
        step_item = {
            'declared_step_id': step_id,
            'session_id': session_id,
            'timestamp': timestamp_val,
            'label': test.get('label', 'unknown'),
            'transcript_text': test.get('matched_text', ''),
            'confidence': confidence_val,
            'video_snippet_uri': '',
            'created_at': int(time.time())
        }
        
        steps_table.put_item(Item=step_item)
        persisted_step_ids.append(step_id)
        logger.info(f"Persisted declared step: {step_id} - {test.get('label')}")
    
    # Step 7: Analyze demeanor
    demeanor_flags = processor.analyze_examiner_demeanor(transcript_data)
    
    # *** PERSIST DEMEANOR FLAGS TO DYNAMODB ***
    persisted_flag_ids = []
    for flag in demeanor_flags:
        flag_id = f"flag_{int(time.time())}_{len(persisted_flag_ids)}"
        
        flag_item = {
            'flag_id': flag_id,
            'session_id': session_id,
            'timestamp': flag.get('timestamp', 0),
            'flag_type': flag.get('flag_type', 'unknown'),
            'transcript_excerpt': flag.get('transcript_excerpt', ''),
            'severity': flag.get('severity', 'low'),
            'description': flag.get('description', ''),
            'created_at': int(time.time())
        }
        
        demeanor_table.put_item(Item=flag_item)
        persisted_flag_ids.append(flag_id)
        logger.info(f"Persisted demeanor flag: {flag_id} - {flag.get('flag_type')}")
    
    # Update session status
    sessions_table.update_item(
        Key={'session_id': session_id},
        UpdateExpression='SET processing_stage = :stage, updated_at = :updated',
        ExpressionAttributeValues={
            ':stage': 'video_analysis',
            ':updated': int(time.time())
        }
    )
    
    logger.info(f"NLP Analysis complete: {len(declared_tests)} tests, {len(demeanor_flags)} flags")
    
    return {
        'session_id': session_id,
        'declared_tests': declared_tests,  # Return for Step Function to map over
        'demeanor_flags': demeanor_flags,
        'persisted_step_ids': persisted_step_ids,
        'persisted_flag_ids': persisted_flag_ids,
        'processing_timestamp': int(time.time()),
        'status': 'completed'
    }


def _extract_json_array_from_model_text(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []

    cleaned = text.strip()
    if cleaned.startswith('```'):
        lines = cleaned.split('\n')
        cleaned = '\n'.join(line for line in lines if not line.startswith('```')).strip()
    if cleaned.startswith('json'):
        cleaned = cleaned[4:].strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        json_match = re.search(r'\[[\s\S]*\]', cleaned)
        if not json_match:
            return []
        try:
            parsed = json.loads(json_match.group())
        except json.JSONDecodeError:
            return []

    if isinstance(parsed, dict):
        parsed = parsed.get('tests') or parsed.get('items') or []
    return parsed if isinstance(parsed, list) else []


def _invoke_test_detection_model(prompt: str, model_id: str) -> str:
    if model_id.startswith('amazon.nova'):
        if not hasattr(bedrock_client, 'converse'):
            raise RuntimeError('bedrock_converse_api_unavailable')
        response = bedrock_client.converse(
            modelId=model_id,
            messages=[{
                'role': 'user',
                'content': [{'text': prompt}],
            }],
            inferenceConfig={
                'maxTokens': 4000,
                'temperature': 0,
            },
        )
        content_blocks = (
            response.get('output', {})
            .get('message', {})
            .get('content', [])
        )
        return '\n'.join(
            block.get('text', '')
            for block in content_blocks
            if isinstance(block, dict) and block.get('text')
        )

    anthropic_model_id = (
        model_id
        if model_id.startswith(('anthropic.', 'us.anthropic.'))
        else DEFAULT_NLP_ANTHROPIC_MODEL_ID
    )
    response = bedrock_client.invoke_model(
        modelId=anthropic_model_id,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            # Thinking is on by default on Sonnet 5 and shares max_tokens.
            "thinking": {"type": "disabled"},
            "max_tokens": 4000,
            "messages": [{
                "role": "user",
                "content": prompt
            }]
        })
    )
    response_body = json.loads(response['body'].read())
    return response_body.get('content', [{}])[0].get('text', '[]')


def enhanced_test_detection_with_ai(transcript_text: str) -> List[Dict[str, Any]]:
    """
    Use Bedrock for enhanced test detection.
    Fallback when pattern matching isn't sufficient.
    """
    try:
        model_id = os.environ.get('CME_NLP_MODEL_ID', DEFAULT_NLP_MODEL_ID)
        prompt = f"""You are analyzing a transcript of a Compulsory Medical Examination (CME). 
Extract EVERY instance where the examiner:
1. Performs a medical test or examination
2. Gives a command that indicates a test (e.g., "move your neck", "raise your leg", "squeeze my hand")
3. Checks, assesses, evaluates, measures, or examines anything
4. Tests strength, sensation, reflexes, range of motion, gait, balance, coordination
5. Palpates, touches, presses, or feels any body part
6. Observes patient movements, posture, or responses

Transcript:
{transcript_text}

For EACH test/examination/assessment, return JSON with:
- test_type: One of: range_of_motion, cervical_rom, lumbar_rom, straight_leg_raise, gait_observation, deep_tendon_reflexes, manual_muscle_testing, light_touch_sensation, pinprick_sensation, vibration_sense, proprioception, palpation, spurlings_test, phalens_test, tinels_sign, babinski_sign, romberg_test, faber_test, neer_test, hawkins_kennedy_test, lachman_test, mcmurray_test, or other appropriate test type
- declaration: The exact words spoken (examiner or patient response indicating test)
- approximate_time: "early" (first 1/3), "middle" (middle 1/3), or "late" (last 1/3) based on position

Be EXTREMELY THOROUGH - extract EVERY test, even if implicit. A 39-minute exam should have 30-60+ tests.
Return ONLY a JSON array, no additional text or explanation:
[{{"test_type": "range_of_motion", "declaration": "move your neck", "approximate_time": "early"}}, ...]"""

        ai_result = _invoke_test_detection_model(prompt, model_id)
        tests = _extract_json_array_from_model_text(ai_result)
        logger.info(f"AI detected {len(tests)} tests using {model_id}")
        return [test for test in tests if isinstance(test, dict)]
        
    except Exception as e:
        logger.error(f"Error in AI-enhanced test detection: {str(e)}")
        return []


def handler(event, context):
    """
    Lambda handler for Step Functions invocation
    """
    try:
        logger.info(f"NLP Processor invoked: {json.dumps(event)}")
        
        session_id = event['session_id']
        transcript_data = event.get('transcript_data')
        
        # If transcript_data not provided, fetch from S3
        if not transcript_data:
            transcript_uri = event.get('transcript_uri')
            if transcript_uri:
                # Download transcript from S3
                import boto3
                s3_client = boto3.client('s3')
                
                # Handle both s3:// and https:// URLs
                if transcript_uri.startswith('s3://'):
                    uri_parts = transcript_uri.replace('s3://', '').split('/', 1)
                    bucket = uri_parts[0]
                    key = uri_parts[1]
                elif transcript_uri.startswith('https://'):
                    # Extract bucket and key from HTTPS URL
                    # Format: https://s3.region.amazonaws.com/bucket/key or https://bucket.s3.region.amazonaws.com/key
                    if 'amazonaws.com' in transcript_uri:
                        # Remove https:// and split
                        uri_without_protocol = transcript_uri.replace('https://', '')
                        if '.s3.' in uri_without_protocol:
                            # Format: bucket.s3.region.amazonaws.com/key
                            parts = uri_without_protocol.split('.s3.', 1)
                            bucket = parts[0]
                            key = parts[1].split('/', 1)[1] if '/' in parts[1] else parts[1]
                        else:
                            # Format: s3.region.amazonaws.com/bucket/key
                            parts = uri_without_protocol.split('/', 1)
                            bucket_key = parts[1] if len(parts) > 1 else ''
                            bucket = bucket_key.split('/')[0]
                            key = '/'.join(bucket_key.split('/')[1:])
                    else:
                        raise ValueError(f"Unsupported transcript URI format: {transcript_uri}")
                else:
                    raise ValueError(f"Unsupported transcript URI format: {transcript_uri}")
                
                logger.info(f"Downloading transcript from s3://{bucket}/{key}")
                response = s3_client.get_object(Bucket=bucket, Key=key)
                transcript_json = response['Body'].read().decode('utf-8')
                transcript_data = json.loads(transcript_json)
                logger.info(f"Loaded transcript with {len(transcript_data.get('results', {}).get('items', []))} items")
        
        # Process transcript
        result = process_transcript_for_cme_analysis(session_id, transcript_data)
        
        return {
            'statusCode': 200,
            **result
        }
        
    except Exception as e:
        logger.error(f"Error in NLP processor handler: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise e
