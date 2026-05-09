# patients/specialty_lists.py
# -----------------------------------------------------------------------------
# Central module holding all quick-pick chip lists per specialty.
# Edit this one file to tweak chip wording or add/remove options.
# No DB changes — these lists are rendered as clickable chips in the templates.
# -----------------------------------------------------------------------------

# General quick-picks (used for every specialty as the base set)
QUICK_PICKS_GENERAL = {
    'chief_complaint': [
        'صداع', 'حمى', 'سعال', 'ألم بطن', 'إقياء',
        'إسهال', 'دوخة', 'تعب عام', 'ضيق نفس', 'ألم صدر',
    ],
    'nursing_notes': [
        'المريض هادئ', 'يظهر عليه تعب', 'يحتاج راحة',
        'ألم خفيف', 'ألم متوسط', 'ألم شديد',
    ],
    'blood_pressure': ['120/80', '130/85', '140/90', '110/70', '150/95'],
    'pulse': ['60', '70', '80', '90', '100', '110'],
    'temperature': ['36.5', '37.0', '37.5', '38.0', '38.5', '39.0'],
    'weight': ['50', '60', '70', '80', '90', '100'],
    'height': ['150', '160', '165', '170', '175', '180'],
    'blood_sugar': ['90', '110', '140', '180', '200', '250'],
    'history_of_present_illness': [
        'بدأت الأعراض منذ ',
        'بشكل تدريجي',
        'بشكل مفاجئ',
        'تتفاقم مع الجهد',
        'تخف مع الراحة',
    ],
    'clinical_examination': [
        'الفحص العام طبيعي',
        'لا يوجد علامات مرضية',
        'بطن طري غير مؤلم',
        'صدر سليم بالإصغاء',
        'علامات حيوية مستقرة',
    ],
    'lab_requests': [
        'CBC', 'تحليل سكر صائم', 'تحليل بول',
        'وظائف كلى', 'وظائف كبد', 'شحوم الدم', 'TSH', 'CRP',
    ],
    'lab_results': [
        'طبيعية', 'في حدود الطبيعي',
        'مرتفعة قليلاً', 'منخفضة قليلاً',
        'بحاجة لإعادة',
    ],
    'imaging_requests': [
        'صورة صدر', 'صورة بطن', 'إيكو بطن',
        'CT scan', 'MRI', 'دوبلر',
    ],
    'imaging_results': [
        'طبيعية', 'لا يوجد علامات مرضية',
        'تحتاج متابعة', 'بحاجة لمزيد من التقييم',
    ],
    'doctor_notes': [
        'الحالة مستقرة', 'تحتاج متابعة',
        'يحتاج لإحالة', 'يحتاج لاستشارة اختصاص',
    ],
    'diagnosis': [
        'التهاب فيروسي', 'التهاب جرثومي',
        'حالة مزمنة', 'حالة حادة',
        'تحت التقييم',
    ],
    'treatment_plan': [
        'علاج عرضي', 'مضاد حيوي',
        'راحة وسوائل', 'متابعة دورية',
        'تعديل الجرعات',
    ],
    'patient_instructions': [
        'تناول الدواء بانتظام',
        'راحة تامة',
        'سوائل كثيرة',
        'متابعة بعد أسبوع',
        'مراجعة طوارئ عند الحاجة',
        'تجنب الجهد البدني',
    ],
    'prescription': [
        'paracetamol 500mg',
        'ibuprofen 400mg',
        'amoxicillin 500mg',
        'omeprazole 20mg',
        'loratadine 10mg',
    ],
}


# Cardiology — extends general
QUICK_PICKS_CARDIOLOGY = {
    **QUICK_PICKS_GENERAL,
    'ecg_results': [
        "نظم جيبي طبيعي",
        "تسرع جيبي",
        "رجفان أذيني",
        "ارتفاع ST",
        "انخفاض ST",
        "موجات T مقلوبة",
    ],
    'clinical_examination': [
        "علامات قلبية طبيعية",
        "نفخة انقباضية",
        "نفخة انبساطية",
        "وذمة طرفية",
        "احتقان رئوي",
    ],
    'ejection_fraction': ['65%', '60%', '55%', '50%', '40%', '35%', '30%'],
    'cardiac_history': [
        'ارتفاع ضغط', 'تصلب شرايين',
        'احتشاء سابق', 'قصور قلب', 'رجفان أذيني',
        'سكري', 'فرط شحوم',
    ],
    'chest_pain_type': [
        'ضاغط', 'حارق', 'طاعن',
        'مفاجئ', 'متقطع', 'مع الجهد',
    ],
    'cardiac_medications': [
        'Aspirin',
        'Clopidogrel',
        'Atorvastatin',
        'Bisoprolol',
        'Lisinopril',
        'Amlodipine',
    ],
    'lab_requests': [
        'LDL, HDL', 'CBC', ' تحليل سكر صائم',
        'وظائف كلى',
    ],
    'imaging_requests': [
        'ECG', 'إيكو قلب', 'إختبار جهد',
        ' CT scan', 'MRI قلب',
    ],
    "prescription": [
            "Aspirin",
            "Clopidogrel",
            "Atorvastatin",
            "Bisoprolol",
            "Lisinopril",
            "ِِAmlodipine",
    ],
    "diagnosis": [
            "ذبحة صدرية مستقرة",
            "ذبحة صدرية غير مستقرة",
            "احتشاء عضلة قلبية حاد (STEMI)",
            "احتشاء عضلة قلبية حاد (NSTEMI)",
            "قصور قلب",
            "ارتفاع ضغط شرياني",
            "رجفان أذيني",
            "التهاب تامور",
    ],        
}


# Orthopedics — extends general
QUICK_PICKS_ORTHOPEDICS = {
    **QUICK_PICKS_GENERAL,
        "chief_complaint": [
            "ألم ظهر", "ألم ركبة", "ألم كتف", "تورم مفصل",
            "تقييد حركة", "إصابة رياضية", "كسر مشتبه",
            "ألم رقبة", "ألم كاحل",
        ],
        "history_of_present_illness": [
            "ألم بدأ بعد سقوط",
            "ألم تدريجي مزمن",
            "ألم بعد إصابة رياضية",
            "ألم يزداد بالحركة",
            "ألم ليلي",
        ],
        'clinical_examination': [
            "تورم واحمرار",
            "كدمات",
            "تقييد حركة نشط",
            "تقييد حركة سلبي",
            "ألم عند الضغط",
            "تشوه واضح",
        ],
        'lab_requests': [
            "CBC", "CRP", "ESR",
            "وظائف كلى", "وظائف كبد",
        ],
        "pain_location": [
            "أسفل الظهر", "أعلى الظهر", "ركبة يمنى", "ركبة يسرى",
            "كتف أيمن", "كتف أيسر", "كاحل أيمن", "كاحل أيسر",
            "مرفق", "رسغ", "ورك", "رقبة",
        ],
        "injury_history": [
            "سقوط من ارتفاع",
            "حادث سير",
            "إصابة رياضية",
            "إجهاد متكرر",
            "بدون رض واضح",
        ],
        "range_of_motion": [
            "مجال حركة طبيعي",
            "محدود مع ألم",
            "محدود بشدة",
            "ثبات تام",
            "ضعف عضلي مرافق",
        ],
        "xray_findings": [
            "لا كسور واضحة",
            "كسر مغلق",
            "كسر مفتوح",
            "خلع",
            "التهاب مفصل تنكسي",
            "تنكس قرص فقري",
            "انزلاق غضروفي",
        ],
        "diagnosis": [
            "التواء", "شد عضلي", "التهاب وتر",
            "خشونة مفصل", "ديسك قطني", "ديسك عنقي",
            "كسر", "خلع كتف", "التهاب جراب",
            "متلازمة النفق الرسغي",
        ],
        "prescription": [
            "Diclofenac 50mg × 2",
            "Naproxen 500mg × 2",
            "Ibuprofen 400mg × 3",
            "Methocarbamol 500mg × 3",
            "Tramadol 50mg PRN",
            "Vitamin D3 50,000 IU أسبوعياً",
            "Calcium + D",
            "Diclofenac gel موضعي",
        ],
        "treatment_plan": [
            "راحة وعدم تحميل",
            "علاج طبيعي",
            "جبيرة",
            "رباط ضاغط",
            "حقنة ستيرويد موضعية",
            "إحالة جراحية",
        ],
        "patient_instructions": [
            "تجنب الجهد ورفع الأثقال",
            "كمادات باردة أول 24 ساعة ثم دافئة",
            "رفع الطرف المصاب",
            "جلسات علاج طبيعي",
            "ارتداء الحذاء الطبي",
        ],
        "imaging_requests": [
            "X-ray للمنطقة المصابة",
            "MRI",
            "CT scan",
            "US للمفصل",
        ],
}


# Neurology — extends general
QUICK_PICKS_NEUROLOGY = {
    **QUICK_PICKS_GENERAL,
        "chief_complaint": [
            "صداع", "دوخة", "خدر", "ضعف طرف",
            "تشنج", "فقدان وعي", "اضطراب رؤية",
            "اضطراب نطق", "ضعف ذاكرة",
        ],
        "history_of_present_illness": [
            "صداع نصفي نابض",
            "نوبة تشنجية معممة",
            "خدر مفاجئ بطرف",
            "ضعف نصفي مفاجئ",
            "نوبة فقدان وعي عابر",
        ],
        "clinical_examination": [
            "GCS 15/15",
            "حركة طبيعية بكامل الأطراف",
            "نقص قوة عضلية بالطرف الأيمن",
            "نقص قوة عضلية بالطرف الأيسر",
            "خدر بالأطراف",
            "شلل وجهي محيطي",
            "اختلال توازن",
            "منعكسات وترية محفوظة",
        ],   
        "imaging_results": [
            "طبيعي",
            "نزف داخل المخ",
            "جلطة دماغية إقفارية",
            "آفة بيضاء (MS)",
            "ضمور دماغي",
            "كتلة مشتبهة",
        ],
        "diagnosis": [
            "شقيقة (Migraine)",
            "صداع توتري",
            "اعتلال أعصاب طرفية",
            "جلطة دماغية",
            "نوبة إقفارية عابرة",
            "صرع",
            "ديسك عنقي",
            "شلل بيل",
        ],
        "prescription": [
            "Sumatriptan 50mg PRN",
            "Paracetamol 1g PRN",
            "Carbamazepine 200mg × 2",
            "Sodium valproate 500mg × 2",
            "Pregabalin 75mg × 2",
            "Aspirin 100mg × 1",
            "Vitamin B complex",
        ],
        "treatment_plan": [
            "علاج عرضي",
            "إحالة لمختص أعصاب",
            "إدخال للمراقبة",
            "ضبط مضادات الصرع",
        ],
        "imaging_requests": [
            "CT brain",
            "MRI brain",
            "MRA / MRV",
            "EEG",
            "EMG / NCV",
            "Carotid Doppler",
        ],
        "lab_requests": [
            "CBC", "B12", "Folate", "Vitamin D",
            "TSH", "Electrolytes", "ESR",
        ],
}


# Dermatology — extends general
QUICK_PICKS_DERMATOLOGY = {
    **QUICK_PICKS_GENERAL,
    "chief_complaint": [
            "حكة", "طفح جلدي", "بثور", "تساقط شعر",
            "تصبغات", "ثآليل", "حب شباب", "تشقق جلد",
            "حروق شمسية",
        ],
        "history_of_present_illness": [
            "ظهر الطفح منذ أيام",
            "حكة ليلية",
            "بدأ بعد دواء جديد",
            "تكرر موسمي",
            "بعد التعرض للشمس",
        ],
        "clinical_examination": [
            "حمامى منتشرة",
            "طفح بقعي حطاطي",
            "آفات حويصلية",
            "تقشر جاف",
            "تصبغات بنية",
            "شرى (Urticaria)",
            "حب شباب التهابي",
            "آفات عقدية",
        ],
        "diagnosis": [
            "إكزيما تأتبية",
            "إكزيما تماسية",
            "صدفية",
            "شرى",
            "حب شباب",
            "ثعلبة بقعية",
            "فطار جلدي",
            "جرب",
            "حزاز مسطح",
        ],
        "prescription": [
            "Hydrocortisone 1% cream × 2",
            "Betamethasone cream × 2",
            "Fucidin cream × 3",
            "Mupirocin ointment",
            "Loratadine 10mg × 1",
            "Cetirizine 10mg × 1",
            "Ketoconazole shampoo",
            "Isotretinoin (under supervision)",
            "Salicylic acid ointment",
        ],
        "treatment_plan": [
            "علاج موضعي",
            "علاج جهازي",
            "تجنب المهيجات",
            "خزعة جلدية",
        ],
        "patient_instructions": [
            "تجنب المهيجات والمواد المعطرة",
            "استخدام مرطب يومي",
            "تجنب التعرض للشمس",
            "استخدام كريم واقي SPF50",
            "تجنب الحك",
        ],
        "lab_requests": [
            "فحص فطريات الجلد",
            "خزعة جلدية",
            "تحليل حساسية",
        ],
        "imaging_requests": [
        ],       
}


# Gynecology & Obstetrics — extends general
QUICK_PICKS_GYNECOLOGY = {
    **QUICK_PICKS_GENERAL,
    'cycle_regularity': ['منتظمة', 'غير منتظمة', 'متأخرة', 'متقدمة'],
    'contraception_method': [
        'لا يوجد', 'حبوب', 'لولب',
        'حقن', 'واقي', 'ربط أنابيب',
    ],
    'obstetric_history': [
        'G1 P0', 'G2 P1', 'G3 P2',
        'إجهاض سابق', 'ولادة قيصرية سابقة', 'ولادة طبيعية',
    ],
    'gestational_age_weeks': ['8', '12', '20', '28', '32', '36', '40'],
    'fundal_height': ['طبيعي', 'أعلى من المتوقع', 'أقل من المتوقع'],
    'abdominal_circumference': ['85', '90', '95', '100', '105'],
    'fetal_heart_rate': ['130', '140', '150', '160', '170'],
    'fetal_movement': ['طبيعية', 'قوية', 'ضعيفة', 'لا توجد'],
    'fetal_position': ['رأسي', 'مقعدي', 'معترض'],
    'ultrasound_notes': [
        'الجنين بحالة جيدة',
        'النمو طبيعي',
        'كمية السائل طبيعية',
        'المشيمة طبيعية',
        'يحتاج متابعة',
    ],
    "diagnosis": [
        "حمل طبيعي",
        "إجهاض مهدد",
        "إجهاض غير مكتمل",
        "تسمم حمل",
        "سكري حمل",
        "انفصال مشيمة",
        "وضعية جنينية غير طبيعية",
    ],
    "prescription": [
        "Folic acid 400mcg × 1",
        "مكملات الحديد 60mg × 1",
        "Metformin 500mg × 2",
        "Labetalol 100mg × 2",
        "Methyldopa 250mg × 3",
        "Insulin (under supervision)",
    ],
    "treatment_plan": [
        "متابعة دورية كل 4 أسابيع",
        "متابعة دورية كل أسبوعين",
        "متابعة أسبوعية",
        "إدخال للمراقبة",
    ],
    "patient_instructions": [
        "تناول الفوليك أسيد يومياً",
        "تناول مكملات الحديد مع فيتامين C",
        "مراقبة حركة الجنين يومياً",
        "الراحة عند الشعور بحركة ضعيفة",
        "مراجعة طوارئ عند نزف أو ألم شديد",
    ],
    "lab_requests": [
        "CBC", "تحليل سكر صائم", "تحليل بول",
        "وظائف كلى", "وظائف كبد", "TSH",
    ],
}


# Dentistry — extends general but overrides a few labels for dental focus
QUICK_PICKS_DENTISTRY = {
    **QUICK_PICKS_GENERAL,
        "chief_complaint": [
            "ألم سن", "تورم لثة", "نزف لثة",
            "حساسية للبارد", "حساسية للحار",
            "خلع سن", "تركيب", "تنظيف وتلميع",
            "تقويم", "اعوجاج إطباق",
        ],
        "nursing_notes": [
            "المريض يأخذ دواء بانتظام",
            "يظهر عليه تعب",
            "مريض سكري",
            "ألم خفيف",
            "ألم متوسط",
            "ألم شديد",
        ],
        "history_of_present_illness": [
            "ألم نابض ليلي",
            "ألم عند المضغ",
            "ألم منتشر للأذن",
            "تورم منذ يومين",
            "نزف لثة عفوي",
        ],
        "clinical_examination": [
            "تسوس عميق على السن X",
            "تورم لثوي موضعي",
            "حساسية للنقر",
            "حركة سن مرضية",
            "تكلسات على الأسنان",
            "خراج لثوي",
        ],
        "diagnosis": [
            "تسوس عميق",
            "التهاب لب سني",
            "خراج سني",
            "التهاب لثة",
            "التهاب نسج داعمة",
            "اعوجاج إطباق",
            "ضرس عقل منطمر",
        ],
        "prescription": [
            "Amoxicillin 500mg × 3",
            "Metronidazole 400mg × 3",
            "Ibuprofen 400mg × 3",
            "Paracetamol 500mg × 3",
            "Chlorhexidine mouthwash × 2",
            "Lidocaine gel",
        ],
        "treatment_plan": [
            "حشو مركب",
            "حشو أملغم",
            "علاج عصب",
            "خلع سن",
            "تركيب تاج",
            "تنظيف وتلميع",
            "تقويم أسنان",
            "زرع أسنان",
        ],
        "patient_instructions": [
            "تجنب الأكل لمدة ساعتين",
            "شطف بمحلول ملحي دافئ",
            "تجنب الأكل من الجهة المعالجة",
            "تنظيف الأسنان مرتين يومياً",
            "خيط أسنان يومياً",
            "مراجعة بعد أسبوع",
        ],
        "imaging_requests": [
            "Periapical X-ray",
            "Panoramic X-ray (OPG)",
            "Bitewing X-ray",
            "CBCT",
        ],
}


# Map specialty key (matches Clinic.specialty values) → quick-picks dict
SPECIALTY_QUICK_PICKS = {
    'general_practice': QUICK_PICKS_GENERAL,
    'cardiology':       QUICK_PICKS_CARDIOLOGY,
    'orthopedics':      QUICK_PICKS_ORTHOPEDICS,
    'neurology':        QUICK_PICKS_NEUROLOGY,
    'dermatology':      QUICK_PICKS_DERMATOLOGY,
    'gynecology':       QUICK_PICKS_GYNECOLOGY,
    'dentistry':        QUICK_PICKS_DENTISTRY,
}


def get_quick_picks(specialty):
    """Return the quick-picks dict for a clinic specialty.

    Falls back to the general-practice list if the specialty is unknown.
    """
    return SPECIALTY_QUICK_PICKS.get(specialty, QUICK_PICKS_GENERAL)


# =============================================================================
# Field manifests — single source of truth for which fields appear where.
# Both display (patient_detail / print) and forms (nurse + doctor) read these
# lists, so adding/removing a field per specialty is a single-file edit.
# =============================================================================

# Arabic labels for every field that may show up in a visit. One dict, all
# specialties — keep keys exactly matching the Visit model's field names.
FIELD_LABELS = {
    # Nurse / vitals
    'chief_complaint':   'الشكوى الرئيسية',
    'nursing_notes':     'ملاحظات تمريضية',
    'blood_pressure':    'ضغط الدم',
    'pulse':             'النبض',
    'temperature':       'الحرارة',
    'weight':            'الوزن',
    'height':            'الطول',
    'blood_sugar':       'سكر الدم',

    # Common medical
    'history_of_present_illness': 'القصة المرضية الحالية',
    'clinical_examination':       'الفحص السريري',
    'lab_requests':               'طلبات التحاليل',
    'lab_results':                'نتائج التحاليل',
    'imaging_requests':           'طلبات الصور',
    'imaging_results':            'نتائج الصور',
    'doctor_notes':               'ملاحظات الطبيب',
    'diagnosis':                  'التشخيص',
    'treatment_plan':             'الخطة العلاجية',
    'patient_instructions':       'تعليمات للمريض',
    'prescription':               'الوصفة الطبية',
    'follow_up_date':             'موعد المراجعة القادم',

    # Cardiology
    'ecg_results':         'نتائج تخطيط القلب',
    'ejection_fraction':   'الكسر القذفي',
    'cardiac_history':     'تاريخ أمراض القلب',
    'chest_pain_type':     'نوع ألم الصدر',
    'cardiac_medications': 'أدوية القلب',

    # Orthopedics
    'pain_location':   'موقع الألم',
    'pain_scale':      'مقياس الألم',
    'injury_history':  'تاريخ الإصابة',
    'range_of_motion': 'مدى الحركة',
    'xray_findings':   'نتائج الأشعة',

    # Neurology
    'CT_MRI_findings':          'نتائج الأشعة المقطعية والرنين المغناطيسي',
    'neurological_examination': 'الفحص العصبي',

    # Dermatology
    'skin_examination': 'فحص الجلد',

    # Gynecology & Obstetrics
    'last_menstrual_period':   'آخر دورة شهرية',
    'cycle_regularity':        'انتظام الدورة',
    'contraception_method':    'وسيلة منع الحمل',
    'obstetric_history':       'تاريخ الولادة',
    'gestational_age_weeks':   'عمر الحمل بالأسابيع',
    'fundal_height':           'ارتفاع قاع الرحم',
    'abdominal_circumference': 'محيط البطن',
    'fetal_heart_rate':        'معدل ضربات قلب الجنين',
    'fetal_movement':          'حركة الجنين',
    'fetal_position':          'وضع الجنين',
    'ultrasound_notes':        'ملاحظات الموجات فوق الصوتية',
}


# Vitals (nursing draft) per specialty.
# chief_complaint and nursing_notes are NOT in this list — they're always shown.
SPECIALTY_NURSING_FIELDS = {
    'general_practice': ['blood_pressure', 'pulse', 'temperature', 'weight', 'height', 'blood_sugar'],
    'cardiology':       ['blood_pressure', 'pulse', 'temperature', 'weight', 'height', 'blood_sugar'],
    'neurology':        ['blood_pressure', 'pulse', 'temperature'],
    'dermatology':      ['blood_pressure', 'pulse', 'temperature'],
    'orthopedics':      ['blood_pressure', 'pulse', 'temperature', 'weight', 'height'],
    'gynecology':       ['blood_pressure', 'pulse', 'temperature', 'weight', 'height', 'blood_sugar'],
    'dentistry':        [],
}


# Specialty-specific medical fields (rendered between clinical_examination and
# the common medical block). Empty list = no specialty-specific fields.
SPECIALTY_MEDICAL_FIELDS = {
    'general_practice': ['imaging_requests', 'imaging_results', 'lab_requests', 'lab_results'],
    'cardiology':       ['lab_requests', 'lab_results', 'ecg_results', 'ejection_fraction', 'cardiac_history',
                         'chest_pain_type', 'cardiac_medications', 'imaging_requests', 'imaging_results'],
    'neurology':        ['lab_requests', 'lab_results', 'imaging_requests', 'imaging_results',],
    'dermatology':      ['lab_requests', 'lab_results', 'imaging_requests', 'imaging_results',],
    'orthopedics':      ['lab_requests', 'lab_results', 'pain_location', 'pain_scale', 'injury_history',
                         'range_of_motion', 'xray_findings', 'imaging_requests', 'imaging_results'],
    'gynecology':       ['lab_requests', 'lab_results', 'last_menstrual_period', 'cycle_regularity',
                         'contraception_method', 'obstetric_history',
                         'gestational_age_weeks', 'fundal_height',
                         'abdominal_circumference', 'fetal_heart_rate',
                         'fetal_movement', 'fetal_position', 'ultrasound_notes'],
    'dentistry':        [],
}


# Common medical fields shown for ALL specialties, in display order.
# Rendered AFTER specialty-specific medical fields.
COMMON_MEDICAL_FIELDS = [
    'doctor_notes',
    'diagnosis',
    'treatment_plan',
    'patient_instructions',
    'prescription',
    'follow_up_date',
]


# Visual styling classes for special rows in patient_detail / print.
FIELD_ROW_CLASSES = {
    'diagnosis':      'highlight',
    'follow_up_date': 'followup',
}


# Every nursing field across all specialties — used by forms to know what
# to drop when a specialty doesn't include a given field.
ALL_NURSING_VITALS = ['blood_pressure', 'pulse', 'temperature',
                      'weight', 'height', 'blood_sugar']


# Every specialty-specific medical field across all specialties — used by
# DoctorVisitForm to drop fields that don't belong to the current specialty.
ALL_SPECIALTY_MEDICAL_FIELDS = sorted({
    f for fields in SPECIALTY_MEDICAL_FIELDS.values() for f in fields
})


def get_nursing_fields(specialty):
    """Return the list of vital field names for a clinic specialty."""
    return SPECIALTY_NURSING_FIELDS.get(specialty,
                                        SPECIALTY_NURSING_FIELDS['general_practice'])


def get_specialty_medical_fields(specialty):
    """Return the list of specialty-specific medical field names."""
    return SPECIALTY_MEDICAL_FIELDS.get(specialty, [])


def build_field_specs(field_names):
    """Turn a flat list of field names into [{'name','label','cls'}, ...]
    consumable by templates and the print payload."""
    return [
        {
            'name':  name,
            'label': FIELD_LABELS.get(name, name),
            'cls':   FIELD_ROW_CLASSES.get(name, ''),
        }
        for name in field_names
    ]


# =============================================================================
# Specialty-aware AI assistance prompts
# -----------------------------------------------------------------------------
# Each entry is the SYSTEM prompt sent to Claude alongside a structured dump
# of the visit data. Tweak wording here without touching views/templates.
# Dentistry intentionally has NO entry — the AI assistant is disabled for it.
# =============================================================================

# Shared guidance appended to every specialty-specific prompt.
#
# IMPORTANT — strict output contract requested by the product owner:
#   * Output ONLY:
#       1) up to 3 suggested diagnoses (most likely first), and
#       2) required tests to confirm them — but ONLY tests not already
#          present in the provided visit data (no repeating what the
#          doctor / nurse already entered).
#   * No guessing — if data is insufficient for a given line, omit it
#     instead of fabricating.
#   * No repeating of the patient data back to the doctor.
#   * No reasoning chains, no introductions, no conclusions, no
#     disclaimers, no extra prose.
#   * Output language: Arabic.
AI_COMMON_GUIDANCE = (
    "أنت مساعد تشخيص للطبيب. أعطِ الإخراج باللغة العربية فقط، "
    "بصيغة مقتضبة جداً (أقل من 100 كلمة)، وبالشكل الصارم التالي حصرياً:\n"
    "التشخيصات المحتملة:\n"
    "1) <التشخيص الأول>\n"
    "2) <التشخيص الثاني — اختياري>\n"
    "3) <التشخيص الثالث — اختياري>\n"
    "الفحوصات المطلوبة:\n"
    "- <الفحص 1>\n"
    "- <الفحص 2>\n"
    "قواعد إلزامية:\n"
    "• اقترح بحد أقصى ثلاثة تشخيصات مرتبة حسب الأرجحية.\n"
    "• اذكر فقط الفحوصات/التحاليل/الصور التي لم يتم توفير نتائجها أو طلبها بالفعل في بيانات الزيارة. "
    "لا تكرر فحصاً موجوداً مسبقاً تحت أي حقل (طلبات التحاليل، نتائج التحاليل، طلبات الصور، نتائج الصور، "
    "تخطيط القلب، الأشعة السينية، الفحص العصبي، فحص الجلد، الإيكو، إلخ).\n"
    "• إذا كانت كل الفحوصات اللازمة متوفرة بالفعل، اكتب: «جميع الفحوصات الضرورية متوفرة».\n"
    "• ممنوع التخمين أو اختلاق قيم. إذا كانت البيانات غير كافية لاقتراح تشخيص ثانٍ أو ثالث، فاكتفِ بما لديك.\n"
    "• ممنوع تكرار أو تلخيص بيانات المريض أو الزيارة.\n"
    "• ممنوع إضافة مقدمات أو خواتم أو إخلاء مسؤولية أو شروحات أو تعليلات.\n"
)

SPECIALTY_AI_PROMPTS = {
    'general_practice': (
        "You are assisting a general-practice physician. Differentials should "
        "lean on common primary-care presentations and step-wise low-cost "
        "workups before advanced imaging.\n\n"
        + AI_COMMON_GUIDANCE
    ),
    'cardiology': (
        "You are assisting a cardiologist. Prioritize high-yield cardiology "
        "differentials when relevant (ACS / NSTEMI / STEMI, heart failure, "
        "arrhythmia, structural disease, hypertensive emergency).\n\n"
        + AI_COMMON_GUIDANCE
    ),
    'orthopedics': (
        "You are assisting an orthopedic surgeon. Distinguish acute trauma "
        "vs. chronic degenerative vs. overuse vs. inflammatory based on "
        "mechanism, pain location/scale, range of motion, neurovascular "
        "status, and X-ray findings when provided.\n\n"
        + AI_COMMON_GUIDANCE
    ),
    'neurology': (
        "You are assisting a neurologist. Localize the lesion (central vs. "
        "peripheral, hemisphere, brainstem, cord, root, plexus, nerve, NMJ, "
        "muscle) when the neuro exam allows. Consider stroke / TIA, "
        "seizure, demyelinating disease, neuropathy, and headache syndromes.\n\n"
        + AI_COMMON_GUIDANCE
    ),
    'dermatology': (
        "You are assisting a dermatologist. Differentials should rest on "
        "lesion morphology, distribution, chronology, triggers, and "
        "patient history. Consider inflammatory, infectious, autoimmune, "
        "and neoplastic etiologies.\n\n"
        + AI_COMMON_GUIDANCE
    ),
    'gynecology': (
        "You are assisting an OB/GYN physician. Distinguish obstetric vs. "
        "gynecological context based on LMP, gestational age, and "
        "obstetric history. For pregnancy follow-up, integrate fundal "
        "height, fetal heart rate, fetal movement, and ultrasound notes.\n\n"
        + AI_COMMON_GUIDANCE
    ),
    # NOTE: 'dentistry' is intentionally absent — AI assist is disabled there.
}


def get_ai_system_prompt(specialty):
    """Return the Claude system prompt for a specialty, or None if the
    specialty has no AI assistance configured (e.g. dentistry)."""
    return SPECIALTY_AI_PROMPTS.get(specialty)
