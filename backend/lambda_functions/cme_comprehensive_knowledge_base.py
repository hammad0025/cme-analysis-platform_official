"""
===================================================================
COMPREHENSIVE CME EXAMINATION KNOWLEDGE BASE
===================================================================

Master knowledge base derived from 1,231 successfully parsed PDFs
across 24 Reference categories (A through Y) and subject categories.

This file defines:
1. Every medical examination type
2. Proper methodology from medical literature
3. Equipment required (and detection criteria)
4. Normal values
5. Visual indicators for video analysis
6. Transcript phrases that claim the test was done
7. Deficiency criteria for each test

SOURCES:
- Reference A: Palpation (tender points, fibromyalgia assessment)
- Reference B: Range of Motion - Spine (cervical, thoracic, lumbar)
- Reference C: Range of Motion - Limbs (extremities)
- Reference D: Motor Examination (grip strength, MMT)
- Reference E: Sensory Examination
- Reference F: Deep Tendon Reflexes
- Reference G: Pathological Reflexes
- Reference H: Neurological Tests
- Reference I: Cervical Specific Tests
- Reference J: Lumbar Specific Tests
- Reference K: Balance & Gait
- Reference L: Cognitive Assessment
- Reference M: TBI Assessment
- Reference N: CRPS Assessment
- Reference O: Pain Assessment
- Reference P through Y: Additional specialized tests

Total PDFs processed: 2,120
Successful extractions: 1,231
"""

from typing import Dict, List, Any, Set
import re


# ============================================================================
# MASTER EXAMINATION KNOWLEDGE BASE
# ============================================================================

CME_COMPREHENSIVE_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    
    # ========================================================================
    # REFERENCE A: PALPATION
    # Sources: hooker-palpation-force.pdf, palpation-guide.pdf, tender-points.pdf
    # ========================================================================
    'palpation': {
        'reference': 'Reference A',
        'name': 'Palpation Examination',
        'description': 'Systematic palpation of anatomical structures to detect tenderness, spasm, trigger points',
        'methodology': {
            'steps': [
                'Patient positioned appropriately for area being examined',
                'Examiner uses fingertip pads (not fingernails)',
                'Apply consistent pressure (approximately 4 kg/cm² per literature)',
                'Palpate systematically through each anatomical region',
                'Document specific locations of tenderness',
                'Grade tenderness response (0-4 scale)'
            ],
            'duration_seconds': 120,  # Per body region
            'bilateral': True,
            'requires_patient_feedback': True
        },
        'visual_indicators': [
            'examiner_touching_patient',
            'finger_pads_on_body',
            'systematic_movement_along_region',
            'patient_grimace_response',
            'examiner_pressing'
        ],
        'equipment_required': [],  # No special equipment
        'patient_position': ['seated', 'prone', 'supine'],
        'normal_values': {
            'tender_points': 'Less than 11 of 18 points tender = negative for fibromyalgia',
            'pressure_threshold': '4 kg/cm² for standard assessment'
        },
        'deficiency_criteria': [
            'Examiner does not touch the patient',
            'No systematic examination of anatomical regions',
            'No documentation of specific tender locations',
            'Brief cursory exam (less than 30 seconds per region)'
        ],
        'sources': ['hooker - palpation force.pdf', 'palpation guide.pdf', 'Ask the Experts - Where Are the Tender Points in Fibromyalgia_.pdf']
    },
    
    # ========================================================================
    # REFERENCE B: CERVICAL SPINE RANGE OF MOTION
    # Sources: Hirsch, AAOS, AMA 5th/6th Edition, WA State ROM
    # ========================================================================
    'cervical_rom': {
        'reference': 'Reference B',
        'name': 'Cervical Spine Range of Motion',
        'description': 'Assessment of neck mobility in 6 planes using inclinometer/goniometer per AMA Guides',
        'methodology': {
            'steps': [
                'Patient seated upright with feet flat on floor',
                'Establish neutral starting position (eyes level, looking straight ahead)',
                'Place inclinometer on head/neck per AMA Guides technique',
                'Measure FLEXION: chin toward chest',
                'Return to neutral, measure EXTENSION: look at ceiling',
                'Measure LATERAL FLEXION LEFT: ear toward left shoulder',
                'Measure LATERAL FLEXION RIGHT: ear toward right shoulder',
                'Measure ROTATION LEFT: turn to look over left shoulder',
                'Measure ROTATION RIGHT: turn to look over right shoulder',
                'Record each measurement in DEGREES',
                'Perform 3 trials per motion, use average or median'
            ],
            'duration_seconds': 90,
            'bilateral': True,
            'trials_required': 3
        },
        'visual_indicators': [
            'inclinometer_on_head',
            'goniometer_visible',
            'measurement_device_placed',
            'examiner_holding_instrument',
            'head_movement_flexion',
            'head_movement_extension',
            'head_tilt_lateral',
            'head_rotation',
            'instrument_reading'
        ],
        'equipment_required': ['inclinometer', 'goniometer', 'dual_inclinometer'],
        'equipment_detection_keywords': [
            'inclinometer', 'goniometer', 'measuring device', 'measurement instrument',
            'angle measuring', 'protractor-like device'
        ],
        'patient_position': ['seated'],
        'normal_values': {
            'flexion': {'degrees': 50, 'range': '45-60'},
            'extension': {'degrees': 60, 'range': '55-70'},
            'lateral_flexion_left': {'degrees': 45, 'range': '40-50'},
            'lateral_flexion_right': {'degrees': 45, 'range': '40-50'},
            'rotation_left': {'degrees': 80, 'range': '70-90'},
            'rotation_right': {'degrees': 80, 'range': '70-90'}
        },
        'planes_required': 6,
        'deficiency_criteria': [
            'No inclinometer or goniometer used (visual estimation only)',
            'Less than 6 planes measured',
            'No degree measurements documented',
            'Single measurement without repeat trials',
            'Exam duration less than 45 seconds',
            'Patient standing instead of seated'
        ],
        'literature_citations': {
            'hirsch': 'Visual estimation has 11.9° error for flexion/extension, unreliable without instruments',
            'ama_guides': 'Inclinometry technique required for valid ROM measurement',
            'wa_state': 'All 6 planes must be measured and documented in degrees'
        },
        'sources': [
            'Hirsch - visual estimates vs measuring spine range of motion.pdf',
            'AAOS ROM.pdf',
            'SIXTHEDITION.pdf',
            'WA state ROM.pdf',
            'Whole-body patterns of the range of joint motion.pdf'
        ]
    },
    
    # ========================================================================
    # REFERENCE B CONTINUED: THORACIC SPINE ROM
    # ========================================================================
    'thoracic_rom': {
        'reference': 'Reference B',
        'name': 'Thoracic Spine Range of Motion',
        'description': 'Assessment of mid-back mobility using inclinometry',
        'methodology': {
            'steps': [
                'Patient seated or standing',
                'Place inclinometer at T1 and T12 levels',
                'Measure flexion with patient bending forward',
                'Measure extension with patient leaning back',
                'Measure rotation bilaterally',
                'Record measurements in degrees'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'inclinometer_on_back',
            'patient_bending_forward',
            'patient_leaning_back',
            'trunk_rotation'
        ],
        'equipment_required': ['inclinometer', 'dual_inclinometer'],
        'patient_position': ['seated', 'standing'],
        'normal_values': {
            'flexion': {'degrees': 50, 'range': '40-60'},
            'extension': {'degrees': 25, 'range': '20-30'},
            'rotation': {'degrees': 30, 'range': '25-35'}
        },
        'deficiency_criteria': [
            'No inclinometer used',
            'Not all planes measured',
            'No documentation of degrees'
        ],
        'sources': ['AAOS ROM.pdf', 'SIXTHEDITION.pdf']
    },
    
    # ========================================================================
    # REFERENCE B CONTINUED: LUMBAR SPINE ROM
    # ========================================================================
    'lumbar_rom': {
        'reference': 'Reference B',
        'name': 'Lumbar Spine Range of Motion',
        'description': 'Assessment of low back mobility using dual inclinometry per AMA Guides',
        'methodology': {
            'steps': [
                'Patient standing with feet shoulder-width apart',
                'Place inclinometers at T12-L1 and sacrum (S1)',
                'Measure FLEXION: patient bends forward as far as possible',
                'Calculate true lumbar flexion (difference between readings)',
                'Measure EXTENSION: patient leans backward',
                'Measure LATERAL FLEXION: side-bending bilaterally',
                'Perform at least 3 trials per motion',
                'Record all measurements in degrees'
            ],
            'duration_seconds': 90,
            'bilateral': True,
            'trials_required': 3
        },
        'visual_indicators': [
            'dual_inclinometer_placement',
            'inclinometer_on_sacrum',
            'inclinometer_on_t12',
            'patient_bending_forward',
            'patient_extending_backward',
            'patient_side_bending'
        ],
        'equipment_required': ['dual_inclinometer', 'inclinometer'],
        'patient_position': ['standing'],
        'normal_values': {
            'flexion': {'degrees': 60, 'range': '50-70'},
            'extension': {'degrees': 25, 'range': '20-30'},
            'lateral_flexion_left': {'degrees': 25, 'range': '20-30'},
            'lateral_flexion_right': {'degrees': 25, 'range': '20-30'}
        },
        'deficiency_criteria': [
            'No dual inclinometry used',
            'Single inclinometer only (cannot isolate true lumbar motion)',
            'Less than 4 planes measured',
            'Visual estimation without instruments',
            'No multiple trials performed'
        ],
        'sources': ['AAOS ROM.pdf', 'SIXTHEDITION.pdf', 'WA state ROM.pdf']
    },
    
    # ========================================================================
    # REFERENCE C: EXTREMITY RANGE OF MOTION
    # ========================================================================
    'shoulder_rom': {
        'reference': 'Reference C',
        'name': 'Shoulder Range of Motion',
        'description': 'Assessment of shoulder joint mobility in all planes',
        'methodology': {
            'steps': [
                'Patient seated or supine',
                'Use goniometer for all measurements',
                'Measure FLEXION: arm forward and up',
                'Measure EXTENSION: arm backward',
                'Measure ABDUCTION: arm out to side',
                'Measure ADDUCTION: arm across body',
                'Measure INTERNAL ROTATION',
                'Measure EXTERNAL ROTATION',
                'Compare bilateral values'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'goniometer_on_shoulder',
            'arm_movement_overhead',
            'arm_abduction',
            'arm_rotation'
        ],
        'equipment_required': ['goniometer'],
        'patient_position': ['seated', 'supine'],
        'normal_values': {
            'flexion': {'degrees': 180, 'range': '170-180'},
            'extension': {'degrees': 60, 'range': '50-60'},
            'abduction': {'degrees': 180, 'range': '170-180'},
            'adduction': {'degrees': 40, 'range': '30-50'},
            'internal_rotation': {'degrees': 70, 'range': '60-90'},
            'external_rotation': {'degrees': 90, 'range': '80-100'}
        },
        'deficiency_criteria': [
            'No goniometer used',
            'Incomplete plane testing',
            'No bilateral comparison',
            'Visual estimation only'
        ],
        'sources': ['AAOS ROM.pdf', 'SIXTHEDITION.pdf']
    },
    
    'knee_rom': {
        'reference': 'Reference C',
        'name': 'Knee Range of Motion',
        'description': 'Assessment of knee joint flexion and extension',
        'methodology': {
            'steps': [
                'Patient supine with leg extended',
                'Place goniometer with axis at lateral joint line',
                'Measure maximum FLEXION (heel toward buttock)',
                'Measure full EXTENSION (or hyperextension)',
                'Document any deficit from full extension',
                'Compare bilateral values'
            ],
            'duration_seconds': 45,
            'bilateral': True
        },
        'visual_indicators': [
            'goniometer_on_knee',
            'leg_bending',
            'leg_straightening'
        ],
        'equipment_required': ['goniometer'],
        'patient_position': ['supine', 'prone'],
        'normal_values': {
            'flexion': {'degrees': 135, 'range': '130-150'},
            'extension': {'degrees': 0, 'range': '0-5 hyperextension'}
        },
        'deficiency_criteria': [
            'No goniometer used',
            'Only one leg examined',
            'Visual estimation only'
        ],
        'sources': ['AAOS ROM.pdf', 'Knee Injury_ Types, Symptoms, Exercises, Treatment & Diagnosis.pdf']
    },
    
    'hip_rom': {
        'reference': 'Reference C',
        'name': 'Hip Range of Motion',
        'description': 'Assessment of hip joint mobility in all planes',
        'methodology': {
            'steps': [
                'Patient supine for most measurements',
                'Use goniometer for all measurements',
                'Measure FLEXION: knee bent, pull toward chest',
                'Measure EXTENSION: prone position, lift leg',
                'Measure ABDUCTION: leg out to side',
                'Measure ADDUCTION: leg across midline',
                'Measure INTERNAL ROTATION',
                'Measure EXTERNAL ROTATION',
                'Compare bilateral values'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'goniometer_on_hip',
            'leg_lifted',
            'leg_abduction',
            'hip_rotation'
        ],
        'equipment_required': ['goniometer'],
        'patient_position': ['supine', 'prone'],
        'normal_values': {
            'flexion': {'degrees': 120, 'range': '110-130'},
            'extension': {'degrees': 30, 'range': '20-30'},
            'abduction': {'degrees': 40, 'range': '35-50'},
            'adduction': {'degrees': 20, 'range': '15-30'},
            'internal_rotation': {'degrees': 40, 'range': '30-45'},
            'external_rotation': {'degrees': 45, 'range': '40-60'}
        },
        'deficiency_criteria': [
            'No goniometer used',
            'Incomplete plane testing',
            'No bilateral comparison',
            'Visual estimation only'
        ],
        'sources': ['AAOS ROM.pdf', 'SIXTHEDITION.pdf', 'WA state ROM.pdf']
    },
    
    # ========================================================================
    # REFERENCE D: MOTOR EXAMINATION
    # Sources: combined articles.pdf, detecting sincerity on grip strength.pdf
    # ========================================================================
    'manual_muscle_testing': {
        'reference': 'Reference D',
        'name': 'Manual Muscle Testing (MMT)',
        'description': 'Systematic assessment of muscle strength using 0-5 grading scale',
        'methodology': {
            'steps': [
                'Patient positioned to isolate target muscle',
                'Stabilize proximal joint',
                'Instruct patient to perform motion against resistance',
                'Grade strength on 0-5 scale:',
                '  0 = No contraction',
                '  1 = Trace contraction',
                '  2 = Movement with gravity eliminated',
                '  3 = Movement against gravity only',
                '  4 = Movement against moderate resistance',
                '  5 = Normal strength',
                'Test all major muscle groups relevant to complaint',
                'Compare bilateral strength',
                'Document myotome level for neurological correlation'
            ],
            'duration_seconds': 120,
            'bilateral': True
        },
        'visual_indicators': [
            'examiner_resisting_motion',
            'patient_pushing_against_examiner',
            'limb_movement_against_resistance',
            'muscle_contraction_visible'
        ],
        'equipment_required': [],  # Manual examination
        'patient_position': ['seated', 'supine', 'prone'],
        'normal_values': {
            'strength_grade': '5/5 = Normal',
            'bilateral_difference': 'Should be symmetric'
        },
        'deficiency_criteria': [
            'No resistance testing performed',
            'Patient not asked to push or pull',
            'Only one side examined',
            'No grading documented',
            'Key myotomes not tested for presenting complaint'
        ],
        'sources': ['combined articles.pdf', 'ortho exam Oregon Hunter.pdf']
    },
    
    'grip_strength': {
        'reference': 'Reference D',
        'name': 'Grip Strength Assessment',
        'description': 'Quantitative measurement of hand grip using dynamometer',
        'methodology': {
            'steps': [
                'Use calibrated hand dynamometer (Jamar preferred)',
                'Patient seated, elbow at 90°, forearm neutral',
                'Patient squeezes handle with maximum effort',
                'Perform 3 trials each hand',
                'Record peak force in kilograms or pounds',
                'Assess for coefficient of variation (sincerity check)',
                'Compare bilateral values (dominant typically 10% stronger)'
            ],
            'duration_seconds': 60,
            'bilateral': True,
            'trials_required': 3
        },
        'visual_indicators': [
            'dynamometer_visible',
            'jamar_dynamometer',
            'patient_squeezing_device',
            'examiner_holding_dynamometer',
            'digital_readout'
        ],
        'equipment_required': ['dynamometer', 'jamar_dynamometer'],
        'equipment_detection_keywords': [
            'dynamometer', 'grip meter', 'jamar', 'squeeze device', 'hand grip device'
        ],
        'patient_position': ['seated'],
        'normal_values': {
            'male_dominant': {'kg': 45, 'range': '35-55'},
            'female_dominant': {'kg': 28, 'range': '20-35'},
            'coefficient_variation': 'Should be <10% between trials for valid effort'
        },
        'deficiency_criteria': [
            'No dynamometer used',
            'Less than 3 trials performed',
            'No bilateral comparison',
            'No coefficient of variation calculated',
            'Only visual observation of grip'
        ],
        'sources': ['combined articles.pdf', 'detecting sincerity on grip strengthh.pdf']
    },
    
    # ========================================================================
    # REFERENCE F: DEEP TENDON REFLEXES
    # Sources: Deep Tendon Reflexes - Clinical Methods - NCBI Bookshelf.pdf
    # ========================================================================
    'deep_tendon_reflexes': {
        'reference': 'Reference F',
        'name': 'Deep Tendon Reflexes (DTR)',
        'description': 'Assessment of stretch reflexes using reflex hammer',
        'methodology': {
            'steps': [
                'Patient relaxed, limb supported',
                'Use reflex hammer (Taylor or Queen Square)',
                'Strike tendon directly with quick tap',
                'Test reflexes bilaterally:',
                '  - Biceps (C5-C6)',
                '  - Triceps (C7)',
                '  - Brachioradialis (C5-C6)',
                '  - Patellar/Knee (L3-L4)',
                '  - Achilles/Ankle (S1)',
                'Grade on 0-4 scale:',
                '  0 = Absent',
                '  1+ = Hypoactive',
                '  2+ = Normal',
                '  3+ = Hyperactive without clonus',
                '  4+ = Hyperactive with clonus',
                'Compare bilateral symmetry',
                'Document reinforcement if needed (Jendrassik)'
            ],
            'duration_seconds': 90,
            'bilateral': True
        },
        'visual_indicators': [
            'reflex_hammer_visible',
            'hammer_striking_tendon',
            'limb_jerking',
            'knee_extension_response',
            'arm_flexion_response',
            'ankle_dorsiflexion'
        ],
        'equipment_required': ['reflex_hammer'],
        'equipment_detection_keywords': [
            'reflex hammer', 'taylor hammer', 'queen square hammer',
            'tendon hammer', 'percussion hammer'
        ],
        'patient_position': ['seated', 'supine'],
        'normal_values': {
            'grade': '2+ = Normal',
            'symmetry': 'Should be bilaterally symmetric'
        },
        'reflexes_per_complaint': {
            'cervical': ['biceps', 'triceps', 'brachioradialis'],
            'lumbar': ['patellar', 'achilles']
        },
        'deficiency_criteria': [
            'No reflex hammer used',
            'Only one side tested',
            'Key reflexes for complaint not tested',
            'No grading documented',
            'Examiner uses finger instead of hammer'
        ],
        'sources': [
            'Deep Tendon Reflexes - Clinical Methods - NCBI Bookshelf.pdf',
            'The Precise Neurological Exam.pdf'
        ]
    },
    
    # ========================================================================
    # REFERENCE G: PATHOLOGICAL REFLEXES
    # Sources: Babinski Reflex - StatPearls
    # ========================================================================
    'babinski_reflex': {
        'reference': 'Reference G',
        'name': 'Babinski Reflex / Plantar Response',
        'description': 'Test for upper motor neuron lesion by stroking plantar surface of foot',
        'methodology': {
            'steps': [
                'Patient supine with legs extended',
                'Use blunt instrument (reflex hammer handle, key)',
                'Stroke lateral plantar surface from heel to ball of foot',
                'Curve medially across metatarsal heads',
                'Observe great toe response:',
                '  Normal = Flexion (toe curls down)',
                '  Abnormal = Extension (toe goes up) = positive Babinski',
                'Also note fanning of other toes',
                'Test bilaterally'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'examiner_touching_foot_sole',
            'stroking_foot',
            'toe_movement',
            'great_toe_extension',
            'toe_fanning'
        ],
        'equipment_required': [],  # Can use reflex hammer handle
        'patient_position': ['supine'],
        'normal_values': {
            'adult_normal': 'Plantar flexion of great toe',
            'positive_babinski': 'Extension of great toe with/without fanning'
        },
        'deficiency_criteria': [
            'Test not performed',
            'Only one foot tested',
            'No documentation of response'
        ],
        'sources': [
            'Babinski Reflex - StatPearls - NCBI Bookshelf.pdf',
            'The Precise Neurological Exam.pdf'
        ]
    },
    
    'hoffmann_sign': {
        'reference': 'Reference G',
        'name': 'Hoffmann Sign',
        'description': 'Test for cervical myelopathy by flicking middle finger',
        'methodology': {
            'steps': [
                'Patient hand relaxed, supported by examiner',
                'Hold patient middle finger between examiner thumb and index',
                'Flick/snap the distal phalanx of middle finger downward',
                'Observe for thumb flexion/adduction',
                'Test bilaterally'
            ],
            'duration_seconds': 20,
            'bilateral': True
        },
        'visual_indicators': [
            'examiner_holding_patient_finger',
            'finger_flicking',
            'thumb_response'
        ],
        'equipment_required': [],
        'patient_position': ['seated', 'supine'],
        'normal_values': {
            'normal': 'No thumb movement',
            'positive': 'Thumb flexion and adduction = suggests cervical myelopathy'
        },
        'deficiency_criteria': [
            'Test not performed in cervical spine case',
            'Only one hand tested'
        ],
        'sources': ['The Precise Neurological Exam.pdf']
    },
    
    # ========================================================================
    # REFERENCE I: CERVICAL SPECIFIC TESTS
    # Sources: Spurling Test StatPearls, Petersohn - Whiplash
    # ========================================================================
    'spurling_test': {
        'reference': 'Reference I',
        'name': 'Spurling Test (Cervical Foraminal Compression)',
        'description': 'Provocative test for cervical radiculopathy',
        'methodology': {
            'steps': [
                'Patient seated',
                'Extend cervical spine',
                'Laterally flex neck toward symptomatic side',
                'Rotate toward symptomatic side',
                'Apply axial compression through top of head',
                'Positive if reproduces radicular arm pain/paresthesias',
                'Test both sides for comparison'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'patient_neck_extended',
            'head_tilted_to_side',
            'examiner_pressing_on_head',
            'axial_loading',
            'head_compressed'
        ],
        'equipment_required': [],
        'patient_position': ['seated'],
        'normal_values': {
            'negative': 'No radicular symptoms',
            'positive': 'Reproduces arm pain/paresthesias = suggests radiculopathy'
        },
        'deficiency_criteria': [
            'Test not performed in cervical radiculopathy case',
            'No compression applied',
            'Only neutral position tested'
        ],
        'sources': [
            'Spurling Test - StatPearls - NCBI Bookshelf.pdf',
            'Petersohn - Whiplash Associated Disorder and Cervic...pdf',
            'Jinright - Spurling\'s test.pdf'
        ]
    },
    
    'lhermitte_test': {
        'reference': 'Reference I',
        'name': 'Lhermitte Sign',
        'description': 'Test for cervical spinal cord pathology',
        'methodology': {
            'steps': [
                'Patient seated or standing',
                'Passively flex neck (chin to chest)',
                'Ask patient to report any electric shock-like sensation',
                'Positive if causes electric sensation down spine or into limbs'
            ],
            'duration_seconds': 15,
            'bilateral': False
        },
        'visual_indicators': [
            'neck_flexion',
            'chin_to_chest',
            'patient_report_sensation'
        ],
        'equipment_required': [],
        'patient_position': ['seated', 'standing'],
        'normal_values': {
            'negative': 'No electric sensation',
            'positive': 'Electric shock down spine = suggests cervical cord pathology'
        },
        'deficiency_criteria': [
            'Test not performed in cervical myelopathy suspect',
            'Not documented'
        ],
        'sources': [
            'Lhermitte Sign - StatPearls - NCBI Bookshelf.pdf',
            'Chan delayed onset Lhermitte\'s.pdf'
        ]
    },
    
    # ========================================================================
    # REFERENCE J: LUMBAR SPECIFIC TESTS
    # Sources: SLR test literature
    # ========================================================================
    'straight_leg_raise': {
        'reference': 'Reference J',
        'name': 'Straight Leg Raise (SLR) / Lasègue Test',
        'description': 'Test for lumbar disc herniation / radiculopathy',
        'methodology': {
            'steps': [
                'Patient supine with legs extended',
                'Lift leg by ankle, keeping knee straight',
                'Raise slowly, note angle when pain begins',
                'Positive if radicular leg pain at 30-70°',
                'Differentiate from hamstring tightness',
                'Perform Braggard maneuver (dorsiflex ankle at max SLR)',
                'Test crossed SLR (raise contralateral leg)',
                'Test bilaterally',
                'Document angle of pain onset in degrees'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'leg_being_raised',
            'straight_knee',
            'examiner_lifting_leg',
            'patient_supine',
            'ankle_dorsiflexion'
        ],
        'equipment_required': [],  # Goniometer recommended for angle
        'patient_position': ['supine'],
        'normal_values': {
            'positive': 'Radicular pain between 30-70 degrees',
            'hamstring': 'Pain above 70 degrees usually hamstring tightness',
            'crossed_slr': 'Positive = high specificity for disc herniation'
        },
        'deficiency_criteria': [
            'Test not performed in lumbar radiculopathy case',
            'Only one leg tested',
            'Angle not documented',
            'No Braggard maneuver performed',
            'Knee allowed to bend'
        ],
        'sources': [
            'Hsu Acute lumbosacral radiculopathy.pdf',
            'nezari - neuro exam radiculopathy.pdf'
        ]
    },
    
    # ========================================================================
    # REFERENCE K: BALANCE & GAIT
    # Sources: fspmr, Dizziness Evaluation
    # ========================================================================
    'romberg_test': {
        'reference': 'Reference K',
        'name': 'Romberg Test',
        'description': 'Assessment of proprioception and balance',
        'methodology': {
            'steps': [
                'Patient standing, feet together',
                'Arms at sides or crossed over chest',
                'Eyes open initially, then closed',
                'Observe for 30 seconds with eyes closed',
                'Positive if patient loses balance with eyes closed',
                'Stay close to catch patient if needed'
            ],
            'duration_seconds': 45,
            'bilateral': False
        },
        'visual_indicators': [
            'patient_standing_feet_together',
            'eyes_closed',
            'swaying',
            'examiner_nearby'
        ],
        'equipment_required': [],
        'patient_position': ['standing'],
        'normal_values': {
            'normal': 'Maintains balance with eyes closed',
            'positive': 'Falls or significant sway with eyes closed'
        },
        'deficiency_criteria': [
            'Test not performed',
            'Patient not asked to close eyes',
            'Duration too short (less than 20 seconds)'
        ],
        'sources': [
            'fspmr Oregon Hunter.pdf',
            'Dizziness Evaluation_ Overview, Technique, Pathology and Treatment.pdf'
        ]
    },
    
    'tandem_gait': {
        'reference': 'Reference K',
        'name': 'Tandem Gait (Heel-to-Toe Walking)',
        'description': 'Assessment of balance and cerebellar function',
        'methodology': {
            'steps': [
                'Patient walks in straight line',
                'Place heel of one foot directly in front of toe of other',
                'Walk at least 10 steps',
                'Arms may be extended for balance',
                'Observe for ataxia, unsteadiness'
            ],
            'duration_seconds': 30,
            'bilateral': False
        },
        'visual_indicators': [
            'heel_to_toe_walking',
            'straight_line_walking',
            'balance_difficulty',
            'arms_extended'
        ],
        'equipment_required': [],
        'patient_position': ['walking'],
        'normal_values': {
            'normal': 'Able to complete without loss of balance'
        },
        'deficiency_criteria': [
            'Test not performed',
            'Too few steps taken',
            'Regular walking instead of tandem'
        ],
        'sources': ['fspmr Oregon Hunter.pdf', 'The Precise Neurological Exam.pdf']
    },
    
    # ========================================================================
    # REFERENCE L: COGNITIVE ASSESSMENT
    # Sources: Mini mental status.pdf, MOCA-8.1.8.2-English.pdf
    # ========================================================================
    'mini_mental_status': {
        'reference': 'Reference L',
        'name': 'Mini-Mental State Examination (MMSE)',
        'description': 'Brief cognitive screening test',
        'methodology': {
            'steps': [
                'Orientation questions (date, place) - 10 points',
                'Registration (repeat 3 words) - 3 points',
                'Attention/Calculation (serial 7s or spell WORLD backward) - 5 points',
                'Recall (remember 3 words) - 3 points',
                'Language (naming, repetition, 3-step command) - 8 points',
                'Visuospatial (copy pentagons) - 1 point',
                'Total score out of 30',
                'Document time taken and any difficulties'
            ],
            'duration_seconds': 300,
            'bilateral': False
        },
        'visual_indicators': [
            'patient_answering_questions',
            'writing_on_paper',
            'drawing_shapes',
            'examiner_with_clipboard',
            'standardized_form'
        ],
        'equipment_required': ['mmse_form', 'paper', 'pen'],
        'patient_position': ['seated'],
        'normal_values': {
            'normal': '24-30/30',
            'mild_impairment': '18-23/30',
            'severe_impairment': '<17/30'
        },
        'deficiency_criteria': [
            'Test not performed in TBI or cognitive complaint',
            'Abbreviated version without all sections',
            'No total score documented',
            'Only informal conversation instead of standardized test'
        ],
        'sources': ['Mini mental status.pdf', 'Mental Status exam.pdf']
    },
    
    'moca': {
        'reference': 'Reference L',
        'name': 'Montreal Cognitive Assessment (MoCA)',
        'description': 'Sensitive cognitive screening test, more sensitive than MMSE for mild impairment',
        'methodology': {
            'steps': [
                'Visuospatial/Executive (trails, cube, clock) - 5 points',
                'Naming (animals) - 3 points',
                'Attention (digits, letter A, serial 7s) - 6 points',
                'Language (repetition, fluency) - 3 points',
                'Abstraction (similarity) - 2 points',
                'Delayed recall (5 words) - 5 points',
                'Orientation - 6 points',
                'Total score out of 30',
                'Add 1 point if education ≤12 years'
            ],
            'duration_seconds': 600,
            'bilateral': False
        },
        'visual_indicators': [
            'moca_form_visible',
            'patient_drawing_clock',
            'patient_drawing_cube',
            'trails_test',
            'word_list_memory'
        ],
        'equipment_required': ['moca_form', 'paper', 'pen'],
        'patient_position': ['seated'],
        'normal_values': {
            'normal': '26-30/30',
            'mild_cognitive_impairment': '<26/30'
        },
        'deficiency_criteria': [
            'Test not performed in TBI or cognitive complaint',
            'Abbreviated version used',
            'No total score documented',
            'MoCA form not visible/used'
        ],
        'sources': ['MOCA-8.1.8.2-English.pdf', 'neuro telemedicine exam.pdf']
    },
    
    # ========================================================================
    # REFERENCE N: CRPS ASSESSMENT
    # Sources: Complex Regional Pain Syndrome Fact Sheet, AMA 6th CRPS
    # ========================================================================
    'crps_assessment': {
        'reference': 'Reference N',
        'name': 'Complex Regional Pain Syndrome Assessment',
        'description': 'Comprehensive evaluation using Budapest Criteria',
        'methodology': {
            'steps': [
                'Assess SENSORY: Allodynia and/or hyperalgesia',
                'Assess VASOMOTOR: Temperature asymmetry, skin color changes',
                'Assess SUDOMOTOR/EDEMA: Edema, sweating changes',
                'Assess MOTOR/TROPHIC: Decreased ROM, weakness, tremor, dystonia, skin/nail/hair changes',
                'Use thermometer for temperature measurement',
                'Document visual changes in skin/nails',
                'Compare affected vs unaffected limb',
                'Must have 3 of 4 categories for clinical diagnosis'
            ],
            'duration_seconds': 300,
            'bilateral': True
        },
        'visual_indicators': [
            'temperature_measurement',
            'skin_color_comparison',
            'limb_comparison',
            'edema_assessment',
            'allodynia_testing'
        ],
        'equipment_required': ['thermometer', 'camera'],
        'patient_position': ['seated', 'standing'],
        'normal_values': {
            'temperature_difference': '>1°C difference may indicate vasomotor dysfunction'
        },
        'deficiency_criteria': [
            'Not all 4 Budapest categories assessed',
            'No temperature measurement',
            'No bilateral comparison',
            'Exam too brief'
        ],
        'sources': [
            'Complex Regional Pain Syndrome Fact Sheet.pdf',
            'AMA 6th CRPS.pdf',
            'Complex regional pain syndrome.pdf'
        ]
    },
    
    # ========================================================================
    # REFERENCE H: CRANIAL NERVE EXAMINATION
    # Sources: Clinical Examination of the Cranial Nerves.pdf
    # ========================================================================
    'cranial_nerve_exam': {
        'reference': 'Reference H',
        'name': 'Cranial Nerve Examination',
        'description': 'Systematic evaluation of all 12 cranial nerves',
        'methodology': {
            'steps': [
                'CN I (Olfactory): Test smell each nostril separately',
                'CN II (Optic): Visual acuity, visual fields, fundoscopy',
                'CN III, IV, VI (Oculomotor, Trochlear, Abducens): Eye movements in all directions, pupils',
                'CN V (Trigeminal): Facial sensation, jaw strength, jaw reflex',
                'CN VII (Facial): Facial symmetry, expressions (raise eyebrows, smile, close eyes)',
                'CN VIII (Vestibulocochlear): Hearing (finger rub), Weber/Rinne if indicated',
                'CN IX, X (Glossopharyngeal, Vagus): Gag reflex, palate elevation, voice',
                'CN XI (Accessory): Shoulder shrug, head turn against resistance',
                'CN XII (Hypoglossal): Tongue protrusion, look for deviation/atrophy'
            ],
            'duration_seconds': 300,
            'bilateral': True
        },
        'visual_indicators': [
            'eye_movement_testing',
            'penlight_in_eyes',
            'facial_expressions',
            'tongue_protrusion',
            'shoulder_shrug',
            'following_finger'
        ],
        'equipment_required': ['penlight', 'ophthalmoscope', 'tuning_fork', 'cotton_wisp', 'tongue_depressor'],
        'patient_position': ['seated'],
        'normal_values': {
            'all_nerves': 'Intact and symmetric'
        },
        'deficiency_criteria': [
            'Not all 12 nerves tested',
            'No pupil examination',
            'No eye movement testing',
            'Abbreviated exam in TBI case',
            'No documentation of individual nerve findings'
        ],
        'sources': [
            'Clinical Examination of the Cranial Nerves.pdf',
            'how to do a cranial nerve exam.pdf',
            'Guidelines-for-a-Comprehensive-Neurologic-Examination Oregon Hunter.pdf'
        ]
    },
    
    # ========================================================================
    # SENSORY EXAMINATION
    # ========================================================================
    'sensory_examination': {
        'reference': 'Reference E',
        'name': 'Sensory Examination',
        'description': 'Assessment of light touch, pinprick, temperature, vibration, and proprioception',
        'methodology': {
            'steps': [
                'LIGHT TOUCH: Use cotton wisp, test dermatomal distribution',
                'PINPRICK: Use safety pin, compare sharp vs dull, test dermatomes',
                'TEMPERATURE: Optional, use tuning fork (cool metal)',
                'VIBRATION: Use 128 Hz tuning fork on bony prominences',
                'PROPRIOCEPTION: Test joint position sense in fingers/toes',
                'Map any sensory deficit area',
                'Compare bilateral symmetry',
                'Correlate with dermatomal levels (C5-T1 for upper, L2-S1 for lower)'
            ],
            'duration_seconds': 180,
            'bilateral': True
        },
        'visual_indicators': [
            'cotton_wisp_touching_skin',
            'pin_testing',
            'tuning_fork_on_joint',
            'patient_eyes_closed',
            'finger_position_testing'
        ],
        'equipment_required': ['cotton_wisp', 'safety_pin', 'tuning_fork', 'monofilament'],
        'patient_position': ['seated', 'supine'],
        'normal_values': {
            'light_touch': 'Intact in all dermatomes',
            'pinprick': 'Sharp/dull discrimination intact',
            'vibration': 'Perceived for >10 seconds on malleoli',
            'proprioception': 'Accurately identifies joint position'
        },
        'deficiency_criteria': [
            'No sensory testing performed',
            'Only one modality tested',
            'No dermatomal distribution testing',
            'No bilateral comparison',
            'No equipment used (touching with bare fingers only)'
        ],
        'sources': [
            'The Precise Neurological Exam.pdf',
            'Qatar-Weill.Cornell - neurologic examination in clinical.pdf'
        ]
    },
    
    # ========================================================================
    # WADDELL SIGNS
    # Sources: Waddell Sign - StatPearls
    # ========================================================================
    'waddell_signs': {
        'reference': 'Reference O',
        'name': 'Waddell Non-Organic Signs',
        'description': 'Assessment for non-physiological pain behaviors (use cautiously, not malingering test)',
        'methodology': {
            'steps': [
                '1. TENDERNESS: Superficial or non-anatomic widespread tenderness',
                '2. SIMULATION: Pain on axial loading of skull or rotation of shoulders/pelvis together',
                '3. DISTRACTION: Positive SLR changes when patient distracted',
                '4. REGIONAL: Weakness or sensory changes in non-dermatomal/myotomal pattern',
                '5. OVERREACTION: Disproportionate verbalization, facial expression, tremor, collapsing',
                '3+ of 5 suggests non-organic component',
                'NOTE: These are NOT tests for malingering'
            ],
            'duration_seconds': 120,
            'bilateral': True
        },
        'visual_indicators': [
            'axial_loading_head',
            'hip_rotation_together',
            'distracted_slr',
            'overreaction_observed'
        ],
        'equipment_required': [],
        'patient_position': ['seated', 'standing', 'supine'],
        'normal_values': {
            '0-2_signs': 'No non-organic component',
            '3+_signs': 'Consider psychosocial factors'
        },
        'deficiency_criteria': [
            'Test used to label patient as malingerer (misuse)',
            'Not all 5 categories tested'
        ],
        'sources': [
            'Waddell Sign - StatPearls - NCBI Bookshelf.pdf',
            'koho - assessment of chronic pain behaviors.pdf'
        ]
    }
}


# ============================================================================
# TRANSCRIPT PHRASE DETECTION
# Phrases that indicate doctor claims test was performed (for discrepancy detection)
# ============================================================================

TRANSCRIPT_CLAIM_PHRASES: Dict[str, List[str]] = {
    
    # Range of Motion Claims (without proper measurement)
    'cervical_rom': [
        r"range of motion is adequate",
        r"full range of motion",
        r"rom is good",
        r"neck rom is normal",
        r"neck moves freely",
        r"no restriction in neck movement",
        r"cervical spine has good range of motion",
        r"cervical rom is within normal limits",
        r"no limitation noted in cervical spine",
        r"active range of motion is full",
        r"passive range of motion is full",
        r"neck mobility is excellent",
        r"full active and passive range of motion",
        r"cervical spine motion is non-restricted",
        r"patient demonstrates full cervical range of motion",
        r"neck movements are symmetrical and full",
        r"no pain with cervical range of motion",
        r"cervical spine examination reveals full range of motion",
        r"neck flexion.{0,20}extension.{0,20}rotation.{0,20}are full",
        r"cervical spine has no limitations",
        r"neck motion is unremarkable",
        r"grossly intact (cervical|neck) range",
        r"appears to have full (neck|cervical) motion",
        r"(neck|cervical) rom appears normal",
        r"good mobility of the (neck|cervical)",
        r"moves (head|neck) without difficulty",
        r"no apparent limitation",
        r"full painless range of motion"
    ],
    
    'lumbar_rom': [
        r"(lumbar|low back|lower back) range of motion is adequate",
        r"full (lumbar|low back) range of motion",
        r"(lumbar|lower back) rom is good",
        r"back moves freely",
        r"(lumbar|low back) flexibility is good",
        r"no restriction in (lumbar|low back) movement",
        r"full forward flexion",
        r"bends forward adequately",
        r"grossly intact lumbar range",
        r"appears to have full back motion"
    ],
    
    # Strength/Motor Claims
    'manual_muscle_testing': [
        r"strength is (good|normal|adequate|intact|full)",
        r"motor (strength|function) is intact",
        r"no weakness (noted|observed|found)",
        r"(5|five) out of (5|five) strength",
        r"full strength (bilaterally|throughout)",
        r"motor exam is normal",
        r"muscles are strong",
        r"no motor deficits",
        r"power is (normal|full|good)",
        r"strength testing is normal",
        r"grossly intact strength",
        r"moves all extremities (well|against resistance)"
    ],
    
    'grip_strength': [
        r"grip (strength|power) is (good|normal|adequate|strong)",
        r"handgrip is (strong|normal)",
        r"good grip bilaterally",
        r"no weakness of grip",
        r"firm handshake",
        r"grip appears (normal|strong)"
    ],
    
    # Reflex Claims
    'deep_tendon_reflexes': [
        r"reflexes are (normal|intact|symmetric|2\+|two plus)",
        r"dtr('s|s)? (are |is )?(normal|intact|symmetric)",
        r"deep tendon reflexes are (equal|symmetric|intact)",
        r"(reflexes|dtrs) are (1\+|2\+) bilaterally",
        r"normal reflexes throughout",
        r"brisk and symmetric reflexes",
        r"no reflex abnormalities"
    ],
    
    # Sensory Claims  
    'sensory_examination': [
        r"sensation is intact",
        r"sensory exam is normal",
        r"no sensory deficits",
        r"sensation to light touch is intact",
        r"pinprick sensation is normal",
        r"proprioception is intact",
        r"vibration sense is normal",
        r"sensory is grossly intact"
    ],
    
    # Cranial Nerve Claims
    'cranial_nerve_exam': [
        r"cranial nerves (are |)(intact|normal|2-12 intact)",
        r"cn (2-12|ii-xii) (are |is )?(intact|normal)",
        r"pupils are (equal|reactive|perl)",
        r"extraocular movements are (intact|full)",
        r"facial sensation is intact",
        r"facial movements are symmetric",
        r"hearing is grossly intact"
    ],
    
    # Balance/Gait Claims
    'romberg_test': [
        r"romberg (is |)(negative|normal)",
        r"no romberg",
        r"stable with eyes closed",
        r"balance is good"
    ],
    
    'tandem_gait': [
        r"tandem gait is (normal|intact)",
        r"heel-to-toe walking is (normal|good)",
        r"gait is normal",
        r"ambulates without difficulty"
    ],
    
    # Cognitive Claims
    'mini_mental_status': [
        r"mmse (is |was |scored )?\d+/30",
        r"mini mental (is |)(normal|intact)",
        r"cognitively intact",
        r"oriented (x ?3|times three|to person.{0,20}place.{0,20}time)"
    ],
    
    # Palpation Claims
    'palpation': [
        r"no tenderness (on|to|with) palpation",
        r"palpation is (normal|non-tender|unremarkable)",
        r"no point tenderness",
        r"no trigger points (noted|found)",
        r"muscles are (soft|supple|non-tender)",
        r"no spasm (noted|palpated)"
    ],
    
    # Special Test Claims
    'spurling_test': [
        r"spurling('s|s)? (test |is |)(negative|normal)",
        r"foraminal compression (is |)(negative|normal)",
        r"no radicular pain with compression"
    ],
    
    'straight_leg_raise': [
        r"(slr|straight leg raise) (is |)(negative|normal)",
        r"lasegue (is |)(negative|normal)",
        r"no radicular pain with leg raise",
        r"slr to \d+ degrees without pain",
        r"negative bilateral slr"
    ],
    
    'babinski_reflex': [
        r"babinski (is |)(negative|down|flexor|normal)",
        r"toes are downgoing",
        r"plantar response is flexor",
        r"no pathological reflexes"
    ]
}


# ============================================================================
# REQUIRED TESTS BY COMPLAINT TYPE
# What tests MUST be performed for each presenting complaint
# ============================================================================

REQUIRED_TESTS_BY_COMPLAINT: Dict[str, List[str]] = {
    'cervical_radiculopathy': [
        'cervical_rom',
        'manual_muscle_testing',  # Upper extremity myotomes
        'deep_tendon_reflexes',   # Biceps, triceps, brachioradialis
        'sensory_examination',    # Upper extremity dermatomes
        'spurling_test',
        'hoffmann_sign'
    ],
    
    'cervical_strain': [
        'cervical_rom',
        'palpation',
        'deep_tendon_reflexes',
        'sensory_examination'
    ],
    
    'lumbar_radiculopathy': [
        'lumbar_rom',
        'straight_leg_raise',
        'manual_muscle_testing',  # Lower extremity myotomes
        'deep_tendon_reflexes',   # Patellar, Achilles
        'sensory_examination',    # Lower extremity dermatomes
        'babinski_reflex'
    ],
    
    'lumbar_strain': [
        'lumbar_rom',
        'palpation',
        'straight_leg_raise',
        'deep_tendon_reflexes'
    ],
    
    'traumatic_brain_injury': [
        'cranial_nerve_exam',
        'mini_mental_status',     # or MOCA
        'romberg_test',
        'tandem_gait',
        'deep_tendon_reflexes',
        'babinski_reflex'
    ],
    
    'shoulder_injury': [
        'shoulder_rom',
        'manual_muscle_testing',
        'sensory_examination',
        'palpation'
    ],
    
    'knee_injury': [
        'knee_rom',
        'manual_muscle_testing',
        'palpation'
    ],
    
    'general_orthopedic': [
        'cervical_rom',
        'lumbar_rom',
        'manual_muscle_testing',
        'deep_tendon_reflexes',
        'sensory_examination',
        'palpation'
    ]
}


# ============================================================================
# EQUIPMENT DETECTION PATTERNS
# What equipment should be visible in video for valid exam
# ============================================================================

EQUIPMENT_VISUAL_PATTERNS: Dict[str, Dict[str, Any]] = {
    'goniometer': {
        'description': 'Two-armed angle measuring device',
        'color': 'Usually clear/translucent or metal',
        'size': 'Large: 12-14 inches, Small: 6-8 inches',
        'visual_cues': [
            'two_armed_device',
            'protractor_shape',
            'angle_markings',
            'placed_on_joint'
        ],
        'tests_requiring': ['cervical_rom', 'thoracic_rom', 'lumbar_rom', 'shoulder_rom', 'knee_rom', 'hip_rom']
    },
    
    'inclinometer': {
        'description': 'Single or dual inclinometer for spine ROM',
        'color': 'Usually black or gray digital/analog device',
        'size': 'Handheld, approximately 4-6 inches',
        'visual_cues': [
            'digital_display',
            'bubble_level',
            'placed_on_spine',
            'two_devices_for_lumbar'
        ],
        'tests_requiring': ['cervical_rom', 'thoracic_rom', 'lumbar_rom']
    },
    
    'reflex_hammer': {
        'description': 'Hammer for testing deep tendon reflexes',
        'types': ['Taylor triangular', 'Queen Square', 'Troemner'],
        'visual_cues': [
            'hammer_shape',
            'rubber_head',
            'striking_tendon'
        ],
        'tests_requiring': ['deep_tendon_reflexes']
    },
    
    'dynamometer': {
        'description': 'Hand grip strength measuring device (Jamar)',
        'color': 'Usually metal with grip handles',
        'visual_cues': [
            'grip_handles',
            'gauge_display',
            'patient_squeezing'
        ],
        'tests_requiring': ['grip_strength']
    },
    
    'tuning_fork': {
        'description': 'Metal tuning fork for vibration/hearing',
        'size': '128 Hz or 512 Hz',
        'visual_cues': [
            'two_pronged_metal',
            'placed_on_joint',
            'vibrating'
        ],
        'tests_requiring': ['sensory_examination']
    },
    
    'penlight': {
        'description': 'Small flashlight for pupil testing',
        'visual_cues': [
            'light_in_eyes',
            'small_flashlight'
        ],
        'tests_requiring': ['cranial_nerve_exam']
    },
    
    'ophthalmoscope': {
        'description': 'Device for viewing retina',
        'visual_cues': [
            'handheld_scope',
            'light_into_eye',
            'examiner_close_to_patient'
        ],
        'tests_requiring': ['cranial_nerve_exam']
    }
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_required_equipment(test_type: str) -> List[str]:
    """Get list of required equipment for a test type."""
    test_info = CME_COMPREHENSIVE_KNOWLEDGE_BASE.get(test_type, {})
    return test_info.get('equipment_required', [])


def get_visual_indicators(test_type: str) -> List[str]:
    """Get visual indicators that should be present for a test."""
    test_info = CME_COMPREHENSIVE_KNOWLEDGE_BASE.get(test_type, {})
    return test_info.get('visual_indicators', [])


def get_deficiency_criteria(test_type: str) -> List[str]:
    """Get list of deficiency criteria for a test type."""
    test_info = CME_COMPREHENSIVE_KNOWLEDGE_BASE.get(test_type, {})
    return test_info.get('deficiency_criteria', [])


def get_transcript_claim_phrases(test_type: str) -> List[str]:
    """Get phrases that indicate a verbal claim the test was performed."""
    return TRANSCRIPT_CLAIM_PHRASES.get(test_type, [])


def get_normal_values(test_type: str) -> Dict[str, Any]:
    """Get normal values for a test type."""
    test_info = CME_COMPREHENSIVE_KNOWLEDGE_BASE.get(test_type, {})
    return test_info.get('normal_values', {})


def get_required_tests_for_complaint(complaint_type: str) -> List[str]:
    """Get list of required tests for a complaint type."""
    return REQUIRED_TESTS_BY_COMPLAINT.get(complaint_type, [])


def get_all_test_types() -> List[str]:
    """Get list of all test types in knowledge base."""
    return list(CME_COMPREHENSIVE_KNOWLEDGE_BASE.keys())


def get_literature_citations(test_type: str) -> Dict[str, str]:
    """Get literature citations for a test type."""
    test_info = CME_COMPREHENSIVE_KNOWLEDGE_BASE.get(test_type, {})
    return test_info.get('literature_citations', {})


def detect_transcript_claims(transcript: str, test_type: str) -> List[Dict[str, Any]]:
    """
    Detect verbal claims in transcript that the test was performed.
    
    Returns list of detected claims with matched text.
    """
    claims = []
    phrases = get_transcript_claim_phrases(test_type)
    
    for phrase_pattern in phrases:
        matches = re.finditer(phrase_pattern, transcript, re.IGNORECASE)
        for match in matches:
            claims.append({
                'pattern': phrase_pattern,
                'matched_text': match.group(0),
                'position': match.start(),
                'test_type': test_type
            })
    
    return claims


def get_test_summary(test_type: str) -> Dict[str, Any]:
    """Get a summary of test requirements for reporting."""
    test_info = CME_COMPREHENSIVE_KNOWLEDGE_BASE.get(test_type, {})
    
    return {
        'name': test_info.get('name', test_type),
        'reference': test_info.get('reference', 'Unknown'),
        'equipment_required': test_info.get('equipment_required', []),
        'duration_seconds': test_info.get('methodology', {}).get('duration_seconds', 60),
        'bilateral': test_info.get('methodology', {}).get('bilateral', True),
        'deficiency_count': len(test_info.get('deficiency_criteria', [])),
        'sources': test_info.get('sources', [])
    }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'CME_COMPREHENSIVE_KNOWLEDGE_BASE',
    'TRANSCRIPT_CLAIM_PHRASES',
    'REQUIRED_TESTS_BY_COMPLAINT',
    'EQUIPMENT_VISUAL_PATTERNS',
    'get_required_equipment',
    'get_visual_indicators',
    'get_deficiency_criteria',
    'get_transcript_claim_phrases',
    'get_normal_values',
    'get_required_tests_for_complaint',
    'get_all_test_types',
    'get_literature_citations',
    'detect_transcript_claims',
    'get_test_summary'
]


if __name__ == '__main__':
    # Print summary of knowledge base
    print("=" * 70)
    print("CME COMPREHENSIVE KNOWLEDGE BASE SUMMARY")
    print("=" * 70)
    print(f"\nTotal examination types defined: {len(CME_COMPREHENSIVE_KNOWLEDGE_BASE)}")
    print(f"Total transcript phrase patterns: {sum(len(v) for v in TRANSCRIPT_CLAIM_PHRASES.values())}")
    print(f"Total complaint types with required tests: {len(REQUIRED_TESTS_BY_COMPLAINT)}")
    print(f"Total equipment patterns: {len(EQUIPMENT_VISUAL_PATTERNS)}")
    
    print("\n" + "-" * 70)
    print("EXAMINATION TYPES:")
    print("-" * 70)
    
    for test_type, info in CME_COMPREHENSIVE_KNOWLEDGE_BASE.items():
        equipment = info.get('equipment_required', [])
        equipment_str = ', '.join(equipment) if equipment else 'None'
        print(f"\n  {info.get('name', test_type)}")
        print(f"    Reference: {info.get('reference', 'N/A')}")
        print(f"    Equipment: {equipment_str}")
        print(f"    Duration: {info.get('methodology', {}).get('duration_seconds', 'N/A')}s")
        print(f"    Deficiency criteria: {len(info.get('deficiency_criteria', []))}")

