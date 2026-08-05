"""
CME Examination Knowledge Base - Derived from Reference PDFs A-Y

This module contains the comprehensive medical examination knowledge base
extracted from the CME Video Recordings reference materials.

Each examination technique includes:
- Proper methodology (how it should be performed)
- Expected visual indicators (what to look for in video)
- Duration expectations
- Equipment required
- Body positions
- Documentation requirements
- Source references from medical literature

Used by cme_video_processor.py for intelligent video analysis.
"""

from typing import Dict, List, Any

# =============================================================================
# COMPREHENSIVE EXAMINATION KNOWLEDGE BASE
# Derived from Reference A-Y PDFs + Subject Area PDFs
# =============================================================================

EXAMINATION_KNOWLEDGE_BASE = {
    # =========================================================================
    # REFERENCE A: PALPATION TECHNIQUES
    # Sources: palpation guide.pdf, hooker - palpation force.pdf, tender points.pdf
    # =========================================================================
    'palpation': {
        'reference': 'Reference A',
        'name': 'Palpation Examination',
        'description': 'Systematic examination by touch to assess tissue texture, tenderness, temperature, and anatomical abnormalities',
        'methodology': {
            'steps': [
                'Patient positioned appropriately for region being examined',
                'Examiner uses fingertips with appropriate pressure (4kg/cm² for tender points)',
                'Systematic palpation following anatomical landmarks',
                'Document location, quality, and intensity of findings',
                'Compare bilateral structures when applicable'
            ],
            'duration_seconds': 30,  # Per region
            'bilateral': True
        },
        'visual_indicators': [
            'examiner_hands_on_patient',
            'systematic_movement_pattern',
            'patient_response_observation',
            'fingertip_pressure_application'
        ],
        'body_regions': {
            'cervical_spine': ['posterior neck', 'paraspinal muscles', 'spinous processes', 'facet joints'],
            'thoracic_spine': ['paraspinal muscles', 'rib angles', 'spinous processes'],
            'lumbar_spine': ['paraspinal muscles', 'SI joints', 'sciatic notch'],
            'tender_points_fibromyalgia': [
                'occiput', 'low cervical', 'trapezius', 'supraspinatus',
                'second rib', 'lateral epicondyle', 'gluteal', 'greater trochanter', 'knee'
            ]
        },
        'equipment_required': [],
        'patient_position': ['seated', 'prone', 'supine'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'expected_findings': ['tenderness', 'muscle spasm', 'trigger points', 'temperature changes', 'swelling'],
        'sources': ['palpation guide.pdf', 'hooker - palpation force.pdf', 'Ask the Experts - Tender Points.pdf']
    },

    # =========================================================================
    # REFERENCE B: RANGE OF MOTION - SPINE
    # Sources: AAOS.pdf, AMA 5th.pdf, AMA inclinometry.pdf, Hirsch visual estimates.pdf
    # =========================================================================
    'cervical_rom': {
        'reference': 'Reference B',
        'name': 'Cervical Spine Range of Motion',
        'description': 'Assessment of neck mobility in all 6 planes using goniometer or inclinometer per AMA Guides',
        'methodology': {
            'steps': [
                'Patient seated upright, looking straight ahead (neutral position)',
                'Place inclinometer/goniometer on patient head',
                'Measure FLEXION: patient brings chin to chest - record degrees',
                'Measure EXTENSION: patient looks up at ceiling - record degrees',
                'Measure LEFT LATERAL FLEXION: patient tilts left ear toward left shoulder - record degrees',
                'Measure RIGHT LATERAL FLEXION: patient tilts right ear toward right shoulder - record degrees',
                'Measure LEFT ROTATION: patient turns head to look over left shoulder - record degrees',
                'Measure RIGHT ROTATION: patient turns head to look over right shoulder - record degrees',
                'Document all 6 measurements in degrees'
            ],
            'duration_seconds': 90,  # Minimum for proper 6-plane measurement
            'bilateral': True
        },
        # CRITICAL: Video detection indicators for each of the 6 planes
        'visual_indicators': [
            # Movement indicators for each plane
            'head_chin_to_chest',           # FLEXION
            'head_looking_up_ceiling',      # EXTENSION  
            'head_tilt_ear_to_shoulder_left',   # LEFT LATERAL FLEXION
            'head_tilt_ear_to_shoulder_right',  # RIGHT LATERAL FLEXION
            'head_turn_look_left',          # LEFT ROTATION
            'head_turn_look_right',         # RIGHT ROTATION
            # Instrument indicators
            'goniometer_on_head',
            'inclinometer_device',
            'measurement_device_in_hand',
            'device_placed_on_patient',
            'examiner_reading_device',
            'recording_measurements'
        ],
        'six_planes_detection': {
            'flexion': {
                'description': 'Chin to chest movement',
                'visual_cue': 'Patient bends head forward, chin moves toward chest',
                'normal_degrees': 50,
                'detection_keywords': ['chin down', 'head forward', 'flexion', 'bend neck forward']
            },
            'extension': {
                'description': 'Looking up at ceiling',
                'visual_cue': 'Patient tilts head backward, looking up',
                'normal_degrees': 60,
                'detection_keywords': ['look up', 'head back', 'extension', 'tilt back']
            },
            'lateral_flexion_left': {
                'description': 'Left ear toward left shoulder',
                'visual_cue': 'Patient tilts head sideways, left ear approaches left shoulder',
                'normal_degrees': 45,
                'detection_keywords': ['tilt left', 'ear to shoulder', 'lateral flexion', 'side bend left']
            },
            'lateral_flexion_right': {
                'description': 'Right ear toward right shoulder',
                'visual_cue': 'Patient tilts head sideways, right ear approaches right shoulder',
                'normal_degrees': 45,
                'detection_keywords': ['tilt right', 'ear to shoulder', 'lateral flexion', 'side bend right']
            },
            'rotation_left': {
                'description': 'Turn to look over left shoulder',
                'visual_cue': 'Patient rotates head to the left, looking over shoulder',
                'normal_degrees': 80,
                'detection_keywords': ['turn left', 'rotate left', 'look left', 'rotation']
            },
            'rotation_right': {
                'description': 'Turn to look over right shoulder',
                'visual_cue': 'Patient rotates head to the right, looking over shoulder',
                'normal_degrees': 80,
                'detection_keywords': ['turn right', 'rotate right', 'look right', 'rotation']
            }
        },
        'instrument_detection': {
            'goniometer': {
                'description': 'Angle measuring device with two arms',
                'visual_cues': ['two-armed device', 'protractor-like', 'placed against head/neck'],
                'indicates_proper_exam': True
            },
            'inclinometer': {
                'description': 'Gravity-based angle device',
                'visual_cues': ['small device on head', 'digital readout', 'fluid-filled'],
                'indicates_proper_exam': True
            },
            'no_instrument': {
                'description': 'Visual estimation only - DEFICIENT per AMA Guides',
                'visual_cues': ['examiner just watching', 'no device visible', 'eyeballing'],
                'indicates_proper_exam': False
            }
        },
        'deficiency_indicators': [
            'no_measurement_device_used',
            'only_visual_estimation',
            'fewer_than_6_planes_tested',
            'no_degrees_documented',
            'exam_too_brief'
        ],
        # ALL the ways doctors describe ROM without actually measuring
        # The AI must detect ANY of these as potential "claimed but not measured"
        'transcript_claim_patterns': {
            'adequate_claims': [
                'range of motion is adequate',
                'rom is adequate',
                'adequate range of motion',
                'adequate rom',
                'range of motion adequate',
                'rom adequate',
                'adequate cervical rom',
                'cervical rom adequate',
            ],
            'full_claims': [
                'full range of motion',
                'full rom',
                'range of motion is full',
                'rom is full',
                'full cervical rom',
                'full neck rom',
                'full cervical range',
                'full range',
                'complete range of motion',
                'complete rom',
            ],
            'normal_claims': [
                'normal range of motion',
                'normal rom',
                'rom is normal',
                'range of motion is normal',
                'within normal limits',
                'wnl',
                'rom wnl',
                'cervical rom normal',
                'normal cervical motion',
                'normal neck motion',
                'grossly normal',
                'grossly normal rom',
            ],
            'good_claims': [
                'good range of motion',
                'good rom',
                'rom is good',
                'range of motion is good',
                'good cervical rom',
                'good neck rom',
                'good mobility',
                'good neck mobility',
                'good cervical mobility',
            ],
            'intact_claims': [
                'intact range of motion',
                'intact rom',
                'rom intact',
                'range of motion intact',
                'cervical rom intact',
                'neck rom intact',
                'mobility intact',
                'movement intact',
                'cervical mobility intact',
            ],
            'unrestricted_claims': [
                'no restriction',
                'no restrictions',
                'unrestricted',
                'unrestricted rom',
                'unrestricted range of motion',
                'no limitation',
                'no limitations',
                'no limited motion',
                'without restriction',
                'without limitation',
                'moves freely',
                'moves neck freely',
                'free movement',
                'free range of motion',
            ],
            'functional_claims': [
                'functional range of motion',
                'functional rom',
                'functionally intact',
                'within functional limits',
                'functional mobility',
                'functional cervical rom',
            ],
            'supple_flexible_claims': [
                'neck supple',
                'supple neck',
                'cervical spine supple',
                'good flexibility',
                'flexible',
                'no stiffness',
                'no cervical stiffness',
                'no neck stiffness',
            ],
            'negative_findings': [
                'no decreased rom',
                'no decreased range of motion',
                'no reduction in rom',
                'no rom deficit',
                'no range of motion deficit',
                'denies stiffness',
                'denies limited motion',
                'negative for decreased rom',
            ],
            'brief_mentions': [
                'rom okay',
                'rom ok',
                'rom fine',
                'range of motion okay',
                'neck moves',
                'can move neck',
                'moves head',
                'head movement okay',
                'cervical motion present',
                'motion present',
                'moves well',
                'moving well',
                'moves appropriately',
            ],
            'vague_claims': [
                'checked range of motion',
                'range of motion checked',
                'rom examined',
                'examined rom',
                'assessed range of motion',
                'rom assessed',
                'evaluated cervical rom',
                'cervical rom evaluated',
                'tested rom',
                'rom tested',
                'reviewed range of motion',
            ],
            'percentage_claims': [
                'rom is 100%',
                '100% rom',
                'full 100% rom',
                '90% rom',
                'near full rom',
                'nearly full range',
                'almost full rom',
                'about full rom',
            ],
            'comparison_claims': [
                'rom comparable to',
                'rom similar to',
                'rom equal bilaterally',
                'symmetric rom',
                'symmetrical rom',
                'bilateral rom equal',
                'equal bilaterally',
            ],
        },
        # Phrases that indicate PROPER measurement was done
        'proper_measurement_indicators': [
            # Degree measurements
            'degrees of flexion',
            'degrees of extension',
            'degrees flexion',
            'degrees extension',
            'degrees of rotation',
            'degrees rotation',
            'degrees of lateral',
            'degrees lateral flexion',
            # Specific numbers
            r'\d+\s*degrees',
            r'\d+°',
            r'flexion\s*[:\-]?\s*\d+',
            r'extension\s*[:\-]?\s*\d+',
            r'rotation\s*[:\-]?\s*\d+',
            r'lateral\s*(flexion|bending)\s*[:\-]?\s*\d+',
            # Instrument mentions
            'inclinometer',
            'goniometer',
            'using inclinometer',
            'using goniometer',
            'measured with',
            'measurement device',
            'digital inclinometer',
            # Specific plane documentation
            'flexion measured at',
            'extension measured at',
            'right rotation',
            'left rotation',
            'right lateral flexion',
            'left lateral flexion',
            'right lateral bending',
            'left lateral bending',
        ],
        'normal_values': {
            'flexion': 50,  # degrees per AAOS
            'extension': 60,
            'lateral_flexion_right': 45,
            'lateral_flexion_left': 45,
            'rotation_right': 80,
            'rotation_left': 80
        },
        'equipment_required': ['inclinometer', 'goniometer'],
        'patient_position': ['seated'],
        'examiner_touch': True,  # Must touch to place device
        'patient_motion_required': True,
        'minimum_exam_duration_seconds': 60,  # Less than this = likely incomplete
        'sources': ['AAOS.pdf', 'AMA 5th.pdf', 'AMA inclinometry.pdf', 'AMA range of motion neck.pdf', 'Hirsch visual estimates.pdf']
    },

    'thoracic_rom': {
        'reference': 'Reference B',
        'name': 'Thoracic Spine Range of Motion',
        'description': 'Assessment of mid-back mobility, primarily rotation',
        'methodology': {
            'steps': [
                'Patient seated with arms crossed over chest',
                'Stabilize pelvis',
                'Measure rotation: turn trunk to each side',
                'Use inclinometer for accurate measurements'
            ],
            'duration_seconds': 45,
            'bilateral': True
        },
        'visual_indicators': [
            'trunk_rotation',
            'seated_position',
            'arms_crossed',
            'measurement_device'
        ],
        'normal_values': {
            'rotation_right': 30,
            'rotation_left': 30
        },
        'equipment_required': ['inclinometer'],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['AMA 5th.pdf', 'AMA range of motion thoracic.pdf']
    },

    'lumbar_rom': {
        'reference': 'Reference B',
        'name': 'Lumbar Spine Range of Motion',
        'description': 'Assessment of low back mobility in all planes',
        'methodology': {
            'steps': [
                'Patient standing for flexion/extension measurements',
                'Use dual inclinometers (T12 and sacrum)',
                'Measure flexion: bend forward at waist',
                'Measure extension: lean backward',
                'Measure lateral flexion: slide hand down leg to each side',
                'Document any pain or limitation'
            ],
            'duration_seconds': 90,
            'bilateral': True
        },
        'visual_indicators': [
            'forward_bending',
            'backward_bending',
            'side_bending',
            'standing_position',
            'dual_inclinometer_placement'
        ],
        'normal_values': {
            'flexion': 60,
            'extension': 25,
            'lateral_flexion_right': 25,
            'lateral_flexion_left': 25
        },
        'equipment_required': ['dual_inclinometers', 'goniometer'],
        'patient_position': ['standing'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['AAOS.pdf', 'AMA 5th.pdf', 'AMA range of motion lumbar.pdf', 'Hirsch visual estimates.pdf']
    },

    # =========================================================================
    # REFERENCE C: RANGE OF MOTION - LIMBS
    # Sources: AAOS ROM.pdf, SIXTHEDITION.pdf
    # =========================================================================
    'shoulder_rom': {
        'reference': 'Reference C',
        'name': 'Shoulder Range of Motion',
        'description': 'Assessment of shoulder joint mobility in all planes',
        'methodology': {
            'steps': [
                'Measure forward flexion: raise arm in front',
                'Measure extension: move arm backward',
                'Measure abduction: raise arm to side',
                'Measure internal rotation: hand behind back',
                'Measure external rotation: arm at side, rotate outward',
                'Use goniometer for measurements'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'arm_raise_forward',
            'arm_raise_sideways',
            'arm_rotation',
            'reaching_behind_back',
            'goniometer_use'
        ],
        'normal_values': {
            'flexion': 180,
            'extension': 60,
            'abduction': 180,
            'internal_rotation': 70,
            'external_rotation': 90
        },
        'equipment_required': ['goniometer'],
        'patient_position': ['standing', 'seated'],
        'examiner_touch': True,  # May assist with passive ROM
        'patient_motion_required': True,
        'sources': ['AAOS ROM.pdf', 'SIXTHEDITION.pdf']
    },

    'elbow_rom': {
        'reference': 'Reference C',
        'name': 'Elbow Range of Motion',
        'description': 'Assessment of elbow flexion, extension, and forearm rotation',
        'methodology': {
            'steps': [
                'Measure flexion: bend elbow fully',
                'Measure extension: straighten elbow',
                'Measure supination: palm up',
                'Measure pronation: palm down'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'elbow_bending',
            'forearm_rotation',
            'palm_position_changes'
        ],
        'normal_values': {
            'flexion': 150,
            'extension': 0,
            'supination': 80,
            'pronation': 80
        },
        'equipment_required': ['goniometer'],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['AAOS ROM.pdf', 'SIXTHEDITION.pdf']
    },

    'wrist_rom': {
        'reference': 'Reference C',
        'name': 'Wrist Range of Motion',
        'description': 'Assessment of wrist joint mobility',
        'methodology': {
            'steps': [
                'Measure flexion: bend wrist down',
                'Measure extension: bend wrist up',
                'Measure radial deviation: toward thumb',
                'Measure ulnar deviation: toward pinky'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'wrist_bending',
            'hand_movement',
            'forearm_stabilization'
        ],
        'normal_values': {
            'flexion': 80,
            'extension': 70,
            'radial_deviation': 20,
            'ulnar_deviation': 30
        },
        'equipment_required': ['goniometer'],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['AAOS ROM.pdf']
    },

    'hip_rom': {
        'reference': 'Reference C',
        'name': 'Hip Range of Motion',
        'description': 'Assessment of hip joint mobility in all planes',
        'methodology': {
            'steps': [
                'Measure flexion: knee to chest (supine)',
                'Measure extension: leg backward (prone or standing)',
                'Measure abduction: leg to side',
                'Measure internal/external rotation: rotate leg'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'leg_lift',
            'knee_to_chest',
            'leg_spread',
            'leg_rotation',
            'lying_position'
        ],
        'normal_values': {
            'flexion': 120,
            'extension': 30,
            'abduction': 45,
            'internal_rotation': 35,
            'external_rotation': 45
        },
        'equipment_required': ['goniometer'],
        'patient_position': ['supine', 'prone'],
        'examiner_touch': True,
        'patient_motion_required': True,
        'sources': ['AAOS ROM.pdf', 'SIXTHEDITION.pdf']
    },

    'knee_rom': {
        'reference': 'Reference C',
        'name': 'Knee Range of Motion',
        'description': 'Assessment of knee flexion and extension',
        'methodology': {
            'steps': [
                'Measure flexion: heel to buttock',
                'Measure extension: full straightening',
                'Document any hyperextension'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'knee_bending',
            'leg_straightening',
            'goniometer_placement'
        ],
        'normal_values': {
            'flexion': 135,
            'extension': 0
        },
        'equipment_required': ['goniometer'],
        'patient_position': ['supine', 'prone'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['AAOS ROM.pdf']
    },

    'ankle_rom': {
        'reference': 'Reference C',
        'name': 'Ankle Range of Motion',
        'description': 'Assessment of ankle dorsiflexion and plantarflexion',
        'methodology': {
            'steps': [
                'Measure dorsiflexion: foot up toward shin',
                'Measure plantarflexion: foot pointed down',
                'Measure inversion and eversion'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'foot_movement',
            'ankle_bending',
            'foot_pointing'
        ],
        'normal_values': {
            'dorsiflexion': 20,
            'plantarflexion': 50,
            'inversion': 35,
            'eversion': 15
        },
        'equipment_required': ['goniometer'],
        'patient_position': ['supine', 'seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['AAOS ROM.pdf']
    },

    # =========================================================================
    # REFERENCE D: MOTOR EXAMINATION
    # Sources: grip strength testing.pdf, muscle grading articles.pdf
    # =========================================================================
    'manual_muscle_testing': {
        'reference': 'Reference D',
        'name': 'Manual Muscle Testing (MMT)',
        'description': 'Assessment of individual muscle strength using standardized grading (0-5)',
        'methodology': {
            'steps': [
                'Position patient to isolate muscle being tested',
                'Stabilize proximal segment',
                'Apply resistance through full ROM',
                'Grade strength: 0=no contraction, 5=normal strength',
                'Test bilateral and compare'
            ],
            'duration_seconds': 120,  # Full exam
            'bilateral': True
        },
        'visual_indicators': [
            'examiner_applying_resistance',
            'patient_pushing_against_resistance',
            'limb_movement_against_resistance',
            'bilateral_comparison'
        ],
        'grading_scale': {
            0: 'No contraction',
            1: 'Trace contraction',
            2: 'Movement with gravity eliminated',
            3: 'Movement against gravity',
            4: 'Movement against resistance',
            5: 'Normal strength'
        },
        'key_muscles': {
            'upper_extremity': ['deltoid', 'biceps', 'triceps', 'wrist_extensors', 'grip'],
            'lower_extremity': ['hip_flexors', 'quadriceps', 'hamstrings', 'ankle_dorsiflexors', 'ankle_plantarflexors']
        },
        'equipment_required': [],
        'patient_position': ['seated', 'supine'],
        'examiner_touch': True,
        'patient_motion_required': True,
        'sources': ['combined articles.pdf', 'grip strength testing reliability.pdf', 'procedures for measuring grip strength.pdf']
    },

    'grip_strength': {
        'reference': 'Reference D',
        'name': 'Grip Strength Testing',
        'description': 'Quantitative assessment of hand grip using dynamometer',
        'methodology': {
            'steps': [
                'Patient seated, elbow at 90 degrees',
                'Forearm in neutral position',
                'Three trials per hand',
                'Average the readings',
                'Compare to normative data'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'dynamometer_in_hand',
            'squeezing_device',
            'seated_position',
            'multiple_attempts'
        ],
        'validity_indicators': {
            'coefficient_of_variation': '<15% indicates valid effort',
            'bell_curve_pattern': 'Second position strongest',
            'bilateral_difference': '<10% typically normal'
        },
        'equipment_required': ['dynamometer', 'Jamar_dynamometer'],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['detecting sincerity on grip strength.pdf', 'grip strength testing reliability.pdf', 'grip strength hard to fake.pdf']
    },

    # =========================================================================
    # REFERENCE E: SENSORY EXAMINATION
    # Sources: The Precise Neurological Exam.pdf
    # =========================================================================
    'light_touch_sensation': {
        'reference': 'Reference E',
        'name': 'Light Touch Sensation Testing',
        'description': 'Assessment of superficial tactile sensation using cotton wisp or fingertip',
        'methodology': {
            'steps': [
                'Patient eyes closed',
                'Apply light touch to dermatomal distribution',
                'Ask patient to identify when touched',
                'Compare bilateral dermatomes',
                'Document any areas of decreased sensation'
            ],
            'duration_seconds': 120,
            'bilateral': True
        },
        'visual_indicators': [
            'patient_eyes_closed',
            'examiner_touching_skin',
            'cotton_wisp_use',
            'systematic_testing_pattern'
        ],
        'dermatome_testing': {
            'C5': 'lateral arm',
            'C6': 'lateral forearm, thumb',
            'C7': 'middle finger',
            'C8': 'medial forearm, small finger',
            'L4': 'medial leg',
            'L5': 'dorsum of foot',
            'S1': 'lateral foot'
        },
        'equipment_required': ['cotton_wisp'],
        'patient_position': ['supine', 'seated'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['The Precise Neurological Exam.pdf']
    },

    'pinprick_sensation': {
        'reference': 'Reference E',
        'name': 'Pinprick Sensation Testing',
        'description': 'Assessment of pain/sharp sensation using disposable pin',
        'methodology': {
            'steps': [
                'Use disposable safety pin or neurotip',
                'Patient eyes closed',
                'Test sharp vs dull discrimination',
                'Follow dermatomal distribution',
                'Compare bilateral'
            ],
            'duration_seconds': 90,
            'bilateral': True
        },
        'visual_indicators': [
            'pin_or_sharp_object',
            'patient_eyes_closed',
            'systematic_dermatomal_testing',
            'patient_verbal_response'
        ],
        'equipment_required': ['neurological_pin', 'safety_pin'],
        'patient_position': ['supine', 'seated'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['The Precise Neurological Exam.pdf']
    },

    'vibration_sense': {
        'reference': 'Reference E',
        'name': 'Vibration Sense Testing',
        'description': 'Assessment of vibration perception using tuning fork',
        'methodology': {
            'steps': [
                'Use 128 Hz tuning fork',
                'Strike fork and place on bony prominence',
                'Ask patient to identify vibration',
                'Test distal to proximal progression',
                'Compare bilateral'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'tuning_fork_use',
            'placement_on_bony_prominences',
            'patient_response',
            'bilateral_comparison'
        ],
        'test_locations': ['great toe IP joint', 'medial malleolus', 'tibial tuberosity', 'finger DIP joints', 'ulnar styloid'],
        'equipment_required': ['tuning_fork_128Hz'],
        'patient_position': ['supine', 'seated'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['The Precise Neurological Exam.pdf']
    },

    'proprioception': {
        'reference': 'Reference E',
        'name': 'Proprioception Testing',
        'description': 'Assessment of joint position sense',
        'methodology': {
            'steps': [
                'Hold digit by sides (not dorsal/plantar)',
                'Patient eyes closed',
                'Move digit up or down',
                'Patient identifies direction',
                'Start distally, move proximal if impaired'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'digit_manipulation',
            'patient_eyes_closed',
            'small_movements_up_down',
            'patient_verbal_response'
        ],
        'equipment_required': [],
        'patient_position': ['supine', 'seated'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['The Precise Neurological Exam.pdf']
    },

    # =========================================================================
    # REFERENCE F: REFLEX EXAMINATION
    # Sources: Deep Tendon Reflexes - NCBI.pdf, Babinski Reflex - StatPearls.pdf
    # =========================================================================
    'deep_tendon_reflexes': {
        'reference': 'Reference F',
        'name': 'Deep Tendon Reflex Testing',
        'description': 'Assessment of muscle stretch reflexes using reflex hammer',
        'methodology': {
            'steps': [
                'Patient relaxed with muscle slightly stretched',
                'Use reflex hammer to tap tendon briskly',
                'Observe for muscle contraction',
                'Grade response 0-4+',
                'Test bilateral and compare',
                'Use Jendrassik maneuver if needed'
            ],
            'duration_seconds': 90,
            'bilateral': True
        },
        'visual_indicators': [
            'reflex_hammer_use',
            'tapping_motion',
            'limb_jerk_response',
            'bilateral_comparison'
        ],
        'grading_scale': {
            0: 'Absent',
            '1+': 'Diminished',
            '2+': 'Normal',
            '3+': 'Increased',
            '4+': 'Clonus'
        },
        'reflexes_tested': {
            'biceps': 'C5-C6',
            'brachioradialis': 'C5-C6',
            'triceps': 'C7-C8',
            'patellar': 'L3-L4',
            'achilles': 'S1'
        },
        'equipment_required': ['reflex_hammer'],
        'patient_position': ['seated', 'supine'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['Deep Tendon Reflexes - Clinical Methods - NCBI Bookshelf.pdf']
    },

    'babinski_sign': {
        'reference': 'Reference F',
        'name': 'Babinski Sign Testing',
        'description': 'Assessment for upper motor neuron lesion by stroking plantar surface',
        'methodology': {
            'steps': [
                'Patient supine with leg extended',
                'Use blunt object along lateral sole',
                'Stroke from heel toward toes',
                'Observe great toe response',
                'Normal: toe flexion; Abnormal: toe extension (upgoing)'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'foot_stroking',
            'toe_movement_observation',
            'examiner_watching_great_toe',
            'bilateral_testing'
        ],
        'interpretation': {
            'normal': 'Great toe flexion (downgoing)',
            'abnormal': 'Great toe extension with fanning of other toes (upgoing)',
            'significance': 'Indicates upper motor neuron lesion if present'
        },
        'equipment_required': ['pointed_object', 'key', 'reflex_hammer_handle'],
        'patient_position': ['supine'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['Babinski Reflex - StatPearls - NCBI Bookshelf.pdf']
    },

    'hoffmanns_sign': {
        'reference': 'Reference F',
        'name': "Hoffman's Sign Testing",
        'description': 'Assessment for cervical myelopathy by flicking middle finger',
        'methodology': {
            'steps': [
                'Hold patient middle finger loosely',
                'Sharply flick distal phalanx downward',
                'Observe for thumb/index flexion',
                'Bilateral comparison essential'
            ],
            'duration_seconds': 20,
            'bilateral': True
        },
        'visual_indicators': [
            'finger_holding',
            'flicking_motion',
            'thumb_flexion_response',
            'bilateral_testing'
        ],
        'interpretation': {
            'normal': 'No thumb/finger flexion',
            'abnormal': 'Flexion of thumb and/or index finger',
            'significance': 'May indicate cervical cord compression'
        },
        'equipment_required': [],
        'patient_position': ['seated'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['Deep Tendon Reflexes - Clinical Methods - NCBI Bookshelf.pdf']
    },

    # =========================================================================
    # REFERENCE G: GAIT EXAMINATION
    # Sources: 10 step gait test.pdf
    # =========================================================================
    'gait_observation': {
        'reference': 'Reference G',
        'name': 'Gait Observation',
        'description': 'Assessment of walking pattern and mobility',
        'methodology': {
            'steps': [
                'Patient walks across room (minimum 20 feet)',
                'Observe from front, side, and behind',
                'Note arm swing, stride length, base of support',
                'Observe turns and transitions',
                'Document any assistive devices used'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'walking',
            'observation_from_multiple_angles',
            'arm_swing',
            'stride_pattern',
            'turning'
        ],
        'gait_abnormalities': {
            'antalgic': 'Shortened stance phase on painful side',
            'ataxic': 'Wide base, irregular steps',
            'spastic': 'Stiff, scissoring pattern',
            'steppage': 'High stepping to clear foot drop',
            'waddling': 'Trunk shifts side to side'
        },
        'equipment_required': [],
        'patient_position': ['standing', 'walking'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['10 step gait test.pdf']
    },

    'tandem_gait': {
        'reference': 'Reference G',
        'name': 'Tandem Gait (Heel-to-Toe Walking)',
        'description': 'Assessment of balance and coordination during narrow base walking',
        'methodology': {
            'steps': [
                'Demonstrate heel-to-toe walking',
                'Patient walks in straight line',
                'Heel of front foot touches toe of back foot',
                'Minimum 10 steps',
                'Note any imbalance or stepping out'
            ],
            'duration_seconds': 45,
            'bilateral': False
        },
        'visual_indicators': [
            'heel_to_toe_placement',
            'straight_line_walking',
            'balance_observation',
            'arm_position'
        ],
        'equipment_required': ['tape_line_optional'],
        'patient_position': ['standing', 'walking'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['10 step gait test.pdf']
    },

    'heel_walking': {
        'reference': 'Reference G',
        'name': 'Heel Walking',
        'description': 'Assessment of L4-L5 nerve root and ankle dorsiflexor strength',
        'methodology': {
            'steps': [
                'Patient walks on heels only',
                'Toes lifted off ground',
                'Walk at least 10-15 feet',
                'Observe for foot drop or difficulty'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'walking_on_heels',
            'toes_elevated',
            'balance_maintenance'
        ],
        'neurological_significance': 'Tests L4-L5 nerve roots and anterior tibialis',
        'equipment_required': [],
        'patient_position': ['standing', 'walking'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['10 step gait test.pdf']
    },

    'toe_walking': {
        'reference': 'Reference G',
        'name': 'Toe Walking',
        'description': 'Assessment of S1 nerve root and gastrocnemius strength',
        'methodology': {
            'steps': [
                'Patient walks on tiptoes only',
                'Heels off ground',
                'Walk at least 10-15 feet',
                'Observe for weakness or difficulty'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'walking_on_tiptoes',
            'heels_elevated',
            'calf_muscle_engagement'
        ],
        'neurological_significance': 'Tests S1 nerve root and gastrocnemius/soleus',
        'equipment_required': [],
        'patient_position': ['standing', 'walking'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['10 step gait test.pdf']
    },

    # =========================================================================
    # REFERENCE H: ROMBERG TEST
    # Sources: Romberg Test - StatPearls - NCBI Bookshelf.pdf
    # =========================================================================
    'romberg_test': {
        'reference': 'Reference H',
        'name': 'Romberg Test',
        'description': 'Assessment of proprioception and posterior column function',
        'methodology': {
            'steps': [
                'Patient stands with feet together',
                'Arms at sides or crossed',
                'Eyes open first - observe stability',
                'Then eyes closed for 30-60 seconds',
                'Stand nearby for safety',
                'Positive if increased sway with eyes closed'
            ],
            'duration_seconds': 90,
            'bilateral': False
        },
        'visual_indicators': [
            'standing_feet_together',
            'eyes_open_then_closed',
            'balance_observation',
            'examiner_nearby_for_safety'
        ],
        'interpretation': {
            'negative': 'Patient maintains balance with eyes closed',
            'positive': 'Significant increase in sway or loss of balance with eyes closed',
            'significance': 'Indicates proprioceptive or vestibular dysfunction'
        },
        'equipment_required': [],
        'patient_position': ['standing'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['Romberg Test - StatPearls - NCBI Bookshelf.pdf']
    },

    # =========================================================================
    # REFERENCE I: COORDINATION TESTING
    # Sources: bell - BESS.pdf, Finger to nose.pdf
    # =========================================================================
    'finger_to_nose': {
        'reference': 'Reference I',
        'name': 'Finger-to-Nose Test',
        'description': 'Assessment of cerebellar function and coordination',
        'methodology': {
            'steps': [
                'Patient touches their nose then examiner finger',
                'Repeat multiple times',
                'Test with eyes open and closed',
                'Observe for intention tremor or dysmetria',
                'Test both arms'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'arm_movement_to_nose',
            'arm_movement_to_examiner_finger',
            'repeated_motion',
            'eyes_closed_phase'
        ],
        'abnormal_findings': {
            'dysmetria': 'Overshooting or undershooting target',
            'intention_tremor': 'Tremor increasing near target',
            'past_pointing': 'Consistently missing target'
        },
        'equipment_required': [],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['Norms for Finger-to-Nose Test.pdf']
    },

    'heel_to_shin': {
        'reference': 'Reference I',
        'name': 'Heel-to-Shin Test',
        'description': 'Assessment of lower extremity coordination',
        'methodology': {
            'steps': [
                'Patient supine or seated',
                'Place heel on opposite knee',
                'Slide heel down shin to ankle',
                'Repeat smoothly',
                'Test both legs'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'heel_on_knee',
            'sliding_motion_down_shin',
            'smooth_controlled_movement',
            'bilateral_testing'
        ],
        'abnormal_findings': {
            'ataxia': 'Irregular, wavering movement',
            'difficulty_keeping_heel_on_shin': 'Suggests cerebellar dysfunction'
        },
        'equipment_required': [],
        'patient_position': ['supine', 'seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['bell - BESS.pdf']
    },

    'rapid_alternating_movements': {
        'reference': 'Reference I',
        'name': 'Rapid Alternating Movements',
        'description': 'Assessment of diadochokinesia - cerebellar function',
        'methodology': {
            'steps': [
                'Patient rapidly pronates/supinates forearm',
                'Hand slaps thigh alternating palm/dorsum',
                'Test foot tapping (heel on floor, tap toes)',
                'Observe for dysdiadochokinesia',
                'Test both sides'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'rapid_hand_movements',
            'alternating_palm_position',
            'foot_tapping',
            'rhythm_observation'
        ],
        'abnormal_findings': {
            'dysdiadochokinesia': 'Irregular, slowed, or clumsy movements',
            'significance': 'Indicates cerebellar dysfunction'
        },
        'equipment_required': [],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['bell - BESS.pdf']
    },

    # =========================================================================
    # REFERENCE J: CRANIAL NERVE EXAMINATION
    # Sources: Clinical Examination of Cranial Nerves.pdf, how to do a cranial nerve exam.pdf
    # =========================================================================
    'cranial_nerve_exam': {
        'reference': 'Reference J',
        'name': 'Cranial Nerve Examination',
        'description': 'Systematic assessment of all 12 cranial nerves',
        'methodology': {
            'steps': [
                'CN I: Test smell (if indicated)',
                'CN II: Visual acuity, visual fields, fundoscopy',
                'CN III, IV, VI: Extraocular movements, pupil responses',
                'CN V: Facial sensation, jaw strength',
                'CN VII: Facial expression, taste',
                'CN VIII: Hearing, vestibular function',
                'CN IX, X: Gag reflex, palate elevation, voice',
                'CN XI: Shoulder shrug, head turn against resistance',
                'CN XII: Tongue protrusion, movement'
            ],
            'duration_seconds': 300,  # 5 minutes for complete exam
            'bilateral': True
        },
        'visual_indicators': [
            'eye_movement_testing',
            'pupil_examination',
            'facial_movement_testing',
            'tongue_examination',
            'shoulder_shrug_testing'
        ],
        'cranial_nerves': {
            'CN_I': {'name': 'Olfactory', 'function': 'Smell'},
            'CN_II': {'name': 'Optic', 'function': 'Vision'},
            'CN_III': {'name': 'Oculomotor', 'function': 'Eye movement, pupil'},
            'CN_IV': {'name': 'Trochlear', 'function': 'Eye movement (down/in)'},
            'CN_V': {'name': 'Trigeminal', 'function': 'Facial sensation, jaw'},
            'CN_VI': {'name': 'Abducens', 'function': 'Eye movement (lateral)'},
            'CN_VII': {'name': 'Facial', 'function': 'Facial expression'},
            'CN_VIII': {'name': 'Vestibulocochlear', 'function': 'Hearing, balance'},
            'CN_IX': {'name': 'Glossopharyngeal', 'function': 'Taste, throat sensation'},
            'CN_X': {'name': 'Vagus', 'function': 'Palate, voice, heart rate'},
            'CN_XI': {'name': 'Accessory', 'function': 'Shoulder, head movement'},
            'CN_XII': {'name': 'Hypoglossal', 'function': 'Tongue movement'}
        },
        'equipment_required': ['penlight', 'visual_acuity_chart', 'tuning_fork', 'tongue_depressor'],
        'patient_position': ['seated'],
        'examiner_touch': True,
        'patient_motion_required': True,
        'sources': ['Clinical Examination of the Cranial Nerves.pdf', 'how to do a cranial nerve exam.pdf', 'Coello CN injury in mild TBI.pdf']
    },

    # =========================================================================
    # REFERENCE K: STRAIGHT LEG RAISE TEST
    # Sources: Rabin - The Sensitivity of the Seated Straight-.pdf
    # =========================================================================
    'straight_leg_raise': {
        'reference': 'Reference K',
        'name': 'Straight Leg Raise Test (Lasègue)',
        'description': 'Assessment for lumbar radiculopathy by stretching sciatic nerve',
        'methodology': {
            'steps': [
                'Patient supine, legs extended',
                'Examiner slowly raises straight leg by ankle',
                'Note angle at which pain occurs',
                'Pain radiating below knee = positive',
                'Document angle and location of symptoms',
                'Test both legs'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'leg_raising',
            'patient_supine',
            'examiner_holding_ankle',
            'pain_response_observation'
        ],
        'interpretation': {
            'positive': 'Radicular pain below knee at 30-70 degrees',
            'negative': 'Only back pain or hamstring tightness',
            'crossed_positive': 'Pain in opposite leg = high specificity'
        },
        'equipment_required': ['goniometer_optional'],
        'patient_position': ['supine'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['Rabin - The Sensitivity of the Seated Straight-...pdf']
    },

    'seated_slr': {
        'reference': 'Reference K',
        'name': 'Seated Straight Leg Raise (Distraction Test)',
        'description': 'SLR performed seated to compare with supine - consistency check',
        'methodology': {
            'steps': [
                'Patient seated on exam table',
                'Extend knee while distracting patient',
                'Compare response to supine SLR',
                'Inconsistency suggests non-organic component'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'seated_position',
            'knee_extension',
            'distraction_technique'
        ],
        'interpretation': {
            'consistent': 'Same response as supine - organic pathology likely',
            'inconsistent': 'Different response - may indicate non-organic factors'
        },
        'equipment_required': [],
        'patient_position': ['seated'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['Rabin - The Sensitivity of the Seated Straight-...pdf']
    },

    # =========================================================================
    # REFERENCE L: ORTHOPEDIC EXAMINATION TECHNIQUES
    # Sources: Lachman Test - StatPearls.pdf, shoulder tests.pdf
    # =========================================================================
    'lachman_test': {
        'reference': 'Reference L',
        'name': 'Lachman Test',
        'description': 'Assessment for anterior cruciate ligament (ACL) integrity',
        'methodology': {
            'steps': [
                'Patient supine, knee flexed 20-30 degrees',
                'Stabilize femur with one hand',
                'Pull tibia forward with other hand',
                'Feel for endpoint and anterior translation',
                'Compare to opposite knee'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'knee_slightly_bent',
            'hands_on_thigh_and_leg',
            'forward_pulling_motion',
            'bilateral_comparison'
        ],
        'interpretation': {
            'positive': 'Soft or absent endpoint, increased translation',
            'grading': '1+ (<5mm), 2+ (5-10mm), 3+ (>10mm)'
        },
        'equipment_required': [],
        'patient_position': ['supine'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['Lachman Test - StatPearls - NCBI Bookshelf.pdf']
    },

    'mcmurray_test': {
        'reference': 'Reference L',
        'name': "McMurray's Test",
        'description': 'Assessment for meniscal tear',
        'methodology': {
            'steps': [
                'Patient supine',
                'Flex hip and knee fully',
                'Externally rotate tibia and extend knee (medial meniscus)',
                'Internally rotate tibia and extend knee (lateral meniscus)',
                'Feel for click or pop with pain'
            ],
            'duration_seconds': 45,
            'bilateral': True
        },
        'visual_indicators': [
            'knee_fully_bent',
            'rotation_of_foot',
            'knee_extension',
            'palpation_of_joint_line'
        ],
        'interpretation': {
            'positive': 'Painful click or pop during extension',
            'medial_meniscus': 'External rotation test',
            'lateral_meniscus': 'Internal rotation test'
        },
        'equipment_required': [],
        'patient_position': ['supine'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['Lachman Test - StatPearls - NCBI Bookshelf.pdf']
    },

    'neer_test': {
        'reference': 'Reference L',
        'name': 'Neer Impingement Test',
        'description': 'Assessment for shoulder subacromial impingement',
        'methodology': {
            'steps': [
                'Examiner stabilizes scapula',
                'Passively forward flex arm in internal rotation',
                'Pain at end range = positive',
                'Indicates subacromial impingement'
            ],
            'duration_seconds': 20,
            'bilateral': True
        },
        'visual_indicators': [
            'arm_raised_overhead',
            'internal_rotation',
            'scapula_stabilization',
            'pain_observation'
        ],
        'equipment_required': [],
        'patient_position': ['seated', 'standing'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['shoulder tests.pdf']
    },

    'hawkins_kennedy_test': {
        'reference': 'Reference L',
        'name': 'Hawkins-Kennedy Test',
        'description': 'Assessment for rotator cuff impingement',
        'methodology': {
            'steps': [
                'Arm forward flexed to 90 degrees',
                'Elbow flexed to 90 degrees',
                'Internally rotate shoulder',
                'Pain = positive for impingement'
            ],
            'duration_seconds': 20,
            'bilateral': True
        },
        'visual_indicators': [
            'arm_at_shoulder_height',
            'elbow_bent',
            'internal_rotation_of_shoulder'
        ],
        'equipment_required': [],
        'patient_position': ['seated', 'standing'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['shoulder tests.pdf']
    },

    'faber_test': {
        'reference': 'Reference L',
        'name': 'FABER Test (Patrick Test)',
        'description': 'Assessment for hip and sacroiliac joint pathology',
        'methodology': {
            'steps': [
                'Patient supine',
                'Place foot on opposite knee (figure-4 position)',
                'Gently press down on flexed knee',
                'Stabilize opposite ASIS',
                'Hip pain = hip pathology; SI pain = SI pathology'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'figure_four_position',
            'knee_pressed_down',
            'pelvis_stabilization'
        ],
        'interpretation': {
            'hip_pathology': 'Pain in groin/hip',
            'SI_pathology': 'Pain in posterior SI region'
        },
        'equipment_required': [],
        'patient_position': ['supine'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['shoulder tests.pdf']
    },

    # =========================================================================
    # REFERENCE M: MENTAL STATUS EXAMINATION
    # Sources: Mental Status exam.pdf, Mini mental status.pdf, MOCA.pdf
    # =========================================================================
    'mental_status_exam': {
        'reference': 'Reference M',
        'name': 'Mental Status Examination',
        'description': 'Assessment of cognitive function and mental state',
        'methodology': {
            'steps': [
                'Assess appearance and behavior',
                'Assess speech and language',
                'Assess mood and affect',
                'Assess thought content and process',
                'Assess perception',
                'Assess cognition (orientation, memory, attention)',
                'Assess insight and judgment'
            ],
            'duration_seconds': 300,
            'bilateral': False
        },
        'visual_indicators': [
            'conversational_assessment',
            'writing_or_drawing',
            'following_commands',
            'recall_testing'
        ],
        'components': {
            'orientation': 'Person, place, time, situation',
            'attention': 'Serial 7s, spell WORLD backward',
            'memory': 'Immediate, short-term, long-term',
            'language': 'Naming, repetition, comprehension',
            'visuospatial': 'Clock drawing, copying figures'
        },
        'equipment_required': ['pen', 'paper', 'standardized_form'],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['Mental Status exam.pdf', 'Mini mental status.pdf']
    },

    'moca_test': {
        'reference': 'Reference M',
        'name': 'Montreal Cognitive Assessment (MoCA)',
        'description': 'Standardized cognitive screening tool',
        'methodology': {
            'steps': [
                'Visuospatial/Executive (trail making, cube copy, clock)',
                'Naming (animals)',
                'Memory (word list)',
                'Attention (digit span, serial 7s, vigilance)',
                'Language (sentence repetition, fluency)',
                'Abstraction (similarities)',
                'Delayed recall',
                'Orientation'
            ],
            'duration_seconds': 600,  # 10 minutes
            'bilateral': False
        },
        'visual_indicators': [
            'paper_form_use',
            'drawing_tasks',
            'verbal_responses',
            'timing_observation'
        ],
        'scoring': {
            'max_score': 30,
            'normal_cutoff': 26,
            'education_adjustment': '+1 for ≤12 years education'
        },
        'equipment_required': ['MoCA_form', 'pen', 'timer'],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['MOCA-8.1.8.2-English.pdf', 'mishra - Montreal cognitive Assessment.pdf']
    },

    # =========================================================================
    # REFERENCE N: NEUROLOGIC TESTS
    # Sources: Spurling Test - StatPearls.pdf, Lhermitte Sign.pdf, cunha - phalen test.pdf
    # =========================================================================
    'spurlings_test': {
        'reference': 'Reference N',
        'name': "Spurling's Test",
        'description': 'Assessment for cervical radiculopathy',
        'methodology': {
            'steps': [
                'Patient seated',
                'Extend neck (look up)',
                'Laterally flex toward symptomatic side',
                'Apply axial compression to head',
                'Reproduction of radicular pain = positive'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'head_tilted_back',
            'head_tilted_sideways',
            'downward_pressure_on_head',
            'pain_response'
        ],
        'interpretation': {
            'positive': 'Reproduction of radicular arm pain',
            'negative': 'Only neck pain or no pain',
            'specificity': 'High (93%)',
            'sensitivity': 'Moderate (30-50%)'
        },
        'equipment_required': [],
        'patient_position': ['seated'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['Spurling Test - StatPearls - NCBI Bookshelf.pdf', "spurling's test.pdf", 'Jinright - Spurling test.pdf']
    },

    'lhermittes_sign': {
        'reference': 'Reference N',
        'name': "Lhermitte's Sign",
        'description': 'Assessment for cervical cord pathology',
        'methodology': {
            'steps': [
                'Patient seated',
                'Flex neck (chin to chest)',
                'Electric shock sensation down spine or limbs = positive',
                'Indicates cervical cord pathology'
            ],
            'duration_seconds': 20,
            'bilateral': False
        },
        'visual_indicators': [
            'neck_flexion',
            'chin_to_chest',
            'patient_response_observation'
        ],
        'interpretation': {
            'positive': 'Electric shock-like sensation radiating down spine or limbs',
            'significance': 'Suggests cervical cord demyelination or compression'
        },
        'equipment_required': [],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['Lhermitte Sign - StatPearls - NCBI Bookshelf.pdf']
    },

    'phalens_test': {
        'reference': 'Reference N',
        'name': "Phalen's Test",
        'description': 'Assessment for carpal tunnel syndrome',
        'methodology': {
            'steps': [
                'Patient holds wrists in full flexion',
                'Dorsal surfaces of hands pressed together',
                'Hold position for 30-60 seconds',
                'Tingling in median nerve distribution = positive'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'wrists_fully_flexed',
            'hands_pressed_together',
            'sustained_position',
            'patient_reporting_symptoms'
        ],
        'interpretation': {
            'positive': 'Paresthesias in thumb, index, middle finger within 60 seconds',
            'sensitivity': '67-83%',
            'specificity': '40-98%'
        },
        'equipment_required': [],
        'patient_position': ['seated', 'standing'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['cunha - phalen test.pdf']
    },

    'tinels_sign': {
        'reference': 'Reference N',
        'name': "Tinel's Sign",
        'description': 'Assessment for nerve entrapment by percussion',
        'methodology': {
            'steps': [
                'Identify nerve pathway (carpal tunnel, cubital tunnel, etc.)',
                'Tap over nerve with finger or reflex hammer',
                'Tingling/electric sensation in nerve distribution = positive',
                'Test at multiple sites if indicated'
            ],
            'duration_seconds': 30,
            'bilateral': True
        },
        'visual_indicators': [
            'tapping_motion',
            'specific_anatomical_location',
            'patient_response'
        ],
        'common_sites': {
            'carpal_tunnel': 'Volar wrist over transverse carpal ligament',
            'cubital_tunnel': 'Medial elbow over ulnar nerve',
            'tarsal_tunnel': 'Medial ankle over posterior tibial nerve'
        },
        'equipment_required': ['reflex_hammer_optional'],
        'patient_position': ['seated'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['cunha - phalen test.pdf']
    },

    # =========================================================================
    # REFERENCE R: CRPS/RSD ASSESSMENT
    # Sources: budapest criteria.pdf, IASP Classification.pdf, AMA 6th CRPS.pdf
    # =========================================================================
    'crps_assessment': {
        'reference': 'Reference R',
        'name': 'Complex Regional Pain Syndrome Assessment',
        'description': 'Assessment for CRPS using Budapest Criteria',
        'methodology': {
            'steps': [
                'Assess for continuing pain disproportionate to inciting event',
                'Evaluate sensory symptoms (allodynia, hyperalgesia)',
                'Evaluate vasomotor signs (temperature/color changes)',
                'Evaluate sudomotor/edema (sweating changes, edema)',
                'Evaluate motor/trophic changes (weakness, tremor, nail/hair changes)',
                'Document signs in at least 2 of 4 categories',
                'Document symptoms in at least 3 of 4 categories'
            ],
            'duration_seconds': 300,
            'bilateral': True  # Compare affected vs unaffected
        },
        'visual_indicators': [
            'skin_color_comparison',
            'temperature_assessment',
            'edema_observation',
            'trophic_changes_observation',
            'allodynia_testing'
        ],
        'budapest_criteria': {
            'sensory': ['Allodynia', 'Hyperalgesia'],
            'vasomotor': ['Temperature asymmetry', 'Color changes'],
            'sudomotor_edema': ['Sweating changes', 'Edema'],
            'motor_trophic': ['Weakness', 'Tremor', 'Dystonia', 'Nail/hair/skin changes']
        },
        'equipment_required': ['thermometer', 'monofilament'],
        'patient_position': ['seated', 'supine'],
        'examiner_touch': True,
        'patient_motion_required': True,
        'sources': ['budapest criteria.pdf', 'IASP Classification of Chronic Pain.pdf', 'AMA 6th CRPS.pdf']
    },

    # =========================================================================
    # REFERENCE U: WADDELL SIGNS
    # Sources: Waddell Sign - StatPearls.pdf
    # =========================================================================
    'waddell_signs': {
        'reference': 'Reference U',
        'name': "Waddell's Signs Assessment",
        'description': 'Assessment of non-organic signs in low back pain',
        'methodology': {
            'steps': [
                'Test superficial tenderness (light skin touch)',
                'Test non-anatomic tenderness (widespread deep tenderness)',
                'Axial loading (press down on skull)',
                'Simulated rotation (rotate shoulders/pelvis together)',
                'Distracted SLR (compare seated vs supine)',
                'Regional disturbances (non-dermatomal weakness/sensory loss)',
                'Overreaction (disproportionate verbal/facial/muscle responses)',
                'Three or more categories positive suggests non-organic component'
            ],
            'duration_seconds': 180,
            'bilateral': True
        },
        'visual_indicators': [
            'light_touch_testing',
            'axial_compression',
            'rotational_testing',
            'distracted_examination',
            'observation_of_responses'
        ],
        'categories': {
            'tenderness': ['Superficial', 'Non-anatomic'],
            'simulation': ['Axial loading', 'Rotation'],
            'distraction': ['SLR comparison'],
            'regional': ['Non-dermatomal weakness', 'Non-dermatomal sensory'],
            'overreaction': ['Disproportionate responses']
        },
        'interpretation': {
            'positive': '3 or more of 5 categories positive',
            'significance': 'Suggests psychological overlay, not malingering'
        },
        'equipment_required': [],
        'patient_position': ['standing', 'seated', 'supine'],
        'examiner_touch': True,
        'patient_motion_required': True,
        'sources': ['Waddell Sign - StatPearls - NCBI Bookshelf.pdf']
    },

    # =========================================================================
    # REFERENCE Y: VESTIBULAR/OCULAR TESTING
    # Sources: Saccades.pdf, Convergence Insufficiency.pdf, VestStudyGuideChart.pdf
    # =========================================================================
    'saccade_testing': {
        'reference': 'Reference Y',
        'name': 'Saccade Testing',
        'description': 'Assessment of rapid eye movements',
        'methodology': {
            'steps': [
                'Patient follows examiner finger jumping between two points',
                'Observe for accuracy of eye movements',
                'Note any overshoot or undershoot',
                'Assess speed of movements'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'rapid_eye_movements',
            'tracking_examiner_finger',
            'horizontal_and_vertical_testing'
        ],
        'abnormal_findings': {
            'hypometric': 'Undershooting target',
            'hypermetric': 'Overshooting target',
            'slow': 'Delayed or sluggish movements'
        },
        'equipment_required': [],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['Saccades.pdf', 'Types of Eye Movements - NCBI Bookshelf.pdf']
    },

    'convergence_testing': {
        'reference': 'Reference Y',
        'name': 'Convergence Testing',
        'description': 'Assessment of eye convergence ability',
        'methodology': {
            'steps': [
                'Hold target at arm length from patient',
                'Slowly move target toward nose',
                'Observe for both eyes tracking inward',
                'Note near point of convergence (NPC)',
                'Normal NPC < 6 cm'
            ],
            'duration_seconds': 45,
            'bilateral': True
        },
        'visual_indicators': [
            'target_moving_toward_face',
            'both_eyes_converging',
            'measurement_of_break_point'
        ],
        'interpretation': {
            'normal': 'NPC < 6 cm with good recovery',
            'abnormal': 'NPC > 10 cm or one eye drifts outward',
            'significance': 'Convergence insufficiency common after TBI'
        },
        'equipment_required': ['fixation_target', 'ruler'],
        'patient_position': ['seated'],
        'examiner_touch': False,
        'patient_motion_required': True,
        'sources': ['Convergence Insufficiency - National Eye Institute.pdf', 'Convergence Insufficiency - AAPOS.pdf']
    },

    'head_impulse_test': {
        'reference': 'Reference Y',
        'name': 'Head Impulse Test (Head Thrust Test)',
        'description': 'Assessment of vestibulo-ocular reflex',
        'methodology': {
            'steps': [
                'Patient fixates on examiner nose',
                'Examiner holds patient head',
                'Rapidly turn head 10-20 degrees to one side',
                'Watch for corrective saccade',
                'Repeat to opposite side'
            ],
            'duration_seconds': 60,
            'bilateral': True
        },
        'visual_indicators': [
            'head_held_by_examiner',
            'rapid_head_movement',
            'eye_fixation_observation',
            'corrective_saccade'
        ],
        'interpretation': {
            'normal': 'Eyes remain fixed on target during head movement',
            'abnormal': 'Catch-up saccade after head turn = vestibular hypofunction'
        },
        'equipment_required': [],
        'patient_position': ['seated'],
        'examiner_touch': True,
        'patient_motion_required': False,
        'sources': ['VestStudyGuideChart..doc.pdf']
    }
}


# =============================================================================
# EXAMINATION CATEGORIES FOR QUICK LOOKUP
# =============================================================================

EXAM_CATEGORIES = {
    'range_of_motion': [
        'cervical_rom', 'thoracic_rom', 'lumbar_rom',
        'shoulder_rom', 'elbow_rom', 'wrist_rom',
        'hip_rom', 'knee_rom', 'ankle_rom'
    ],
    'neurological': [
        'deep_tendon_reflexes', 'babinski_sign', 'hoffmanns_sign',
        'light_touch_sensation', 'pinprick_sensation', 'vibration_sense', 'proprioception',
        'cranial_nerve_exam', 'romberg_test'
    ],
    'motor': [
        'manual_muscle_testing', 'grip_strength'
    ],
    'coordination': [
        'finger_to_nose', 'heel_to_shin', 'rapid_alternating_movements'
    ],
    'gait': [
        'gait_observation', 'tandem_gait', 'heel_walking', 'toe_walking'
    ],
    'orthopedic': [
        'straight_leg_raise', 'seated_slr', 'lachman_test', 'mcmurray_test',
        'neer_test', 'hawkins_kennedy_test', 'faber_test',
        'spurlings_test', 'lhermittes_sign', 'phalens_test', 'tinels_sign'
    ],
    'cognitive': [
        'mental_status_exam', 'moca_test'
    ],
    'special': [
        'palpation', 'crps_assessment', 'waddell_signs'
    ],
    'vestibular_ocular': [
        'saccade_testing', 'convergence_testing', 'head_impulse_test'
    ]
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_exam_by_name(exam_name: str) -> Dict[str, Any]:
    """Get examination details by name (flexible matching)"""
    exam_name_lower = exam_name.lower().replace(' ', '_').replace('-', '_')
    
    # Direct match
    if exam_name_lower in EXAMINATION_KNOWLEDGE_BASE:
        return EXAMINATION_KNOWLEDGE_BASE[exam_name_lower]
    
    # Partial match
    for key, value in EXAMINATION_KNOWLEDGE_BASE.items():
        if exam_name_lower in key or key in exam_name_lower:
            return value
        if exam_name_lower in value.get('name', '').lower():
            return value
    
    return {}


def get_exams_by_category(category: str) -> List[Dict[str, Any]]:
    """Get all examinations in a category"""
    exam_names = EXAM_CATEGORIES.get(category, [])
    return [EXAMINATION_KNOWLEDGE_BASE.get(name, {}) for name in exam_names]


def get_visual_indicators(exam_name: str) -> List[str]:
    """Get expected visual indicators for video analysis"""
    exam = get_exam_by_name(exam_name)
    return exam.get('visual_indicators', [])


def get_expected_duration(exam_name: str) -> int:
    """Get expected duration in seconds"""
    exam = get_exam_by_name(exam_name)
    return exam.get('methodology', {}).get('duration_seconds', 30)


def requires_examiner_touch(exam_name: str) -> bool:
    """Check if exam requires examiner to touch patient"""
    exam = get_exam_by_name(exam_name)
    return exam.get('examiner_touch', False)


def requires_patient_motion(exam_name: str) -> bool:
    """Check if exam requires patient active movement"""
    exam = get_exam_by_name(exam_name)
    return exam.get('patient_motion_required', False)


def get_all_exam_names() -> List[str]:
    """Get list of all examination names"""
    return list(EXAMINATION_KNOWLEDGE_BASE.keys())


def get_reference_sources(exam_name: str) -> List[str]:
    """Get PDF source references for an examination"""
    exam = get_exam_by_name(exam_name)
    return exam.get('sources', [])


# =============================================================================
# VIDEO ANALYSIS HELPERS
# =============================================================================

def get_motion_expectations(exam_name: str) -> Dict[str, Any]:
    """
    Get motion expectations formatted for video processor compatibility.
    This maintains backward compatibility with existing TEST_MOTION_EXPECTATIONS format.
    """
    exam = get_exam_by_name(exam_name)
    
    if not exam:
        return {}
    
    return {
        'expected_movements': exam.get('visual_indicators', []),
        'patient_motion_required': exam.get('patient_motion_required', False),
        'examiner_touch': exam.get('examiner_touch', False),
        'description': exam.get('description', ''),
        'duration_seconds': exam.get('methodology', {}).get('duration_seconds', 30),
        'reference': exam.get('reference', ''),
        'sources': exam.get('sources', [])
    }


def build_test_motion_expectations() -> Dict[str, Dict[str, Any]]:
    """
    Build TEST_MOTION_EXPECTATIONS dict from knowledge base.
    This can replace the hardcoded dict in cme_video_processor.py
    """
    expectations = {}
    
    for exam_name in get_all_exam_names():
        expectations[exam_name] = get_motion_expectations(exam_name)
    
    return expectations


# Export for use by cme_video_processor.py
TEST_MOTION_EXPECTATIONS_FROM_KB = build_test_motion_expectations()


if __name__ == '__main__':
    # Test the knowledge base
    print("=" * 70)
    print("CME EXAMINATION KNOWLEDGE BASE")
    print("=" * 70)
    print(f"\nTotal examinations: {len(EXAMINATION_KNOWLEDGE_BASE)}")
    print(f"Categories: {list(EXAM_CATEGORIES.keys())}")
    print()
    
    # Print by category
    for category, exams in EXAM_CATEGORIES.items():
        print(f"\n{category.upper()} ({len(exams)} exams):")
        for exam in exams:
            data = EXAMINATION_KNOWLEDGE_BASE.get(exam, {})
            print(f"  - {exam}: {data.get('name', 'Unknown')}")
            print(f"    Reference: {data.get('reference', 'N/A')}")
            print(f"    Duration: {data.get('methodology', {}).get('duration_seconds', 'N/A')}s")

