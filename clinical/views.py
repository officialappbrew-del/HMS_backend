from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from .models import ConsultationNote, Prescription, VitalSign, EarlyWarningScore, VitalSignAlert
from .serializers import (
    ConsultationNoteSerializer, PrescriptionSerializer, VitalSignSerializer,
    EarlyWarningScoreSerializer, VitalSignAlertSerializer,
    PrescriptionInteractionCheckSerializer, MedicationHistorySerializer,
)
from core.views import TenantScopedModelViewSet
from patients.models import Patient
from core.permissions import IsDoctor, IsPharmacist, IsNurse, IsDoctorOrPharmacist, IsDoctorOrNurse, IsClinicalStaff


class ConsultationNoteViewSet(TenantScopedModelViewSet):
    queryset = ConsultationNote.objects.all()
    serializer_class = ConsultationNoteSerializer
    permission_classes = [IsDoctor]

    def get_queryset(self):
        queryset = super().get_queryset().select_related('patient', 'doctor', 'visit')
        visit_id = self.request.query_params.get('visit')
        if visit_id:
            queryset = queryset.filter(visit_id=visit_id)
        return queryset

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(doctor=user.tenant_user)


class PrescriptionViewSet(TenantScopedModelViewSet):
    queryset = Prescription.objects.all()
    serializer_class = PrescriptionSerializer
    permission_classes = [IsDoctorOrPharmacist]

    def get_queryset(self):
        queryset = super().get_queryset().select_related('patient', 'prescribed_by', 'dispensed_by', 'visit')
        visit_id = self.request.query_params.get('visit')
        if visit_id:
            queryset = queryset.filter(visit_id=visit_id)
        patient_id = self.request.query_params.get('patient')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        prescription_status = self.request.query_params.get('status')
        if prescription_status:
            queryset = queryset.filter(status=prescription_status)
        return queryset

    def perform_create(self, serializer):
        tenant = self._get_request_tenant()
        if not tenant:
            raise PermissionDenied("Tenant context required.")
        
        validated_data = serializer.validated_data.copy()
        visit = validated_data.get('visit')
        if visit and not validated_data.get('patient'):
            validated_data['patient'] = visit.patient
        
        serializer.save(**validated_data)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(prescribed_by=user.tenant_user)

    @action(detail=False, methods=['get'], url_path='history')
    def medication_history(self, request):
        patient_id = request.query_params.get('patient')
        if not patient_id:
            return Response({'detail': 'patient is required.'}, status=status.HTTP_400_BAD_REQUEST)

        patient = Patient.objects.filter(pk=patient_id).first()
        if not patient:
            return Response({'detail': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)

        history_items = []
        for prescription in Prescription.objects.filter(patient=patient).order_by('-prescribed_date'):
            history_items.append({
                'id': prescription.id,
                'drug_name': prescription.drug_name,
                'dosage': prescription.dosage,
                'frequency': prescription.frequency,
                'duration': prescription.duration,
                'route': prescription.route,
                'status': prescription.status,
                'prescribed_date': prescription.prescribed_date.isoformat(),
            })

        warnings = []
        seen_drugs = {}
        for item in history_items:
            drug_name = (item.get('drug_name') or '').strip()
            if not drug_name:
                continue
            normalized = drug_name.lower()
            if normalized in seen_drugs:
                warnings.append({
                    'type': 'duplicate_drug',
                    'message': f"Medication '{drug_name}' appears multiple times in the patient history. Review for duplicate therapy or overdose risk.",
                    'drug_name': drug_name,
                })
            else:
                seen_drugs[normalized] = item

        if len(seen_drugs) > 1:
            warnings.append({
                'type': 'duplicate_class',
                'message': 'Multiple medications are present in the patient history; review for duplicate therapy.',
            })

        serializer = MedicationHistorySerializer({
            'patient_id': patient.id,
            'medications': history_items,
            'warnings': warnings,
        })
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='interaction-check')
    def interaction_check(self, request):
        serializer = PrescriptionInteractionCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        drug_names = serializer.validated_data.get('drug_names') or []
        prescription_ids = serializer.validated_data.get('prescription_ids') or []

        interactions = []
        if prescription_ids:
            prescriptions = Prescription.objects.filter(pk__in=prescription_ids)
            drug_names = [item.drug_name for item in prescriptions if item.drug_name]

        known_pairs = {
            ('warfarin', 'aspirin'): 'High risk of bleeding.',
            ('warfarin', 'ibuprofen'): 'High risk of bleeding.',
            ('amiodarone', 'simvastatin'): 'Risk of myopathy.',
            ('lithium', 'ibuprofen'): 'Risk of lithium toxicity.',
            ('digoxin', 'clarithromycin'): 'Potential digoxin toxicity.',
            ('metformin', 'cimetidine'): 'Risk of hypoglycemia.',
        }

        normalized = [name.lower() for name in drug_names if name]
        for index, drug_a in enumerate(normalized):
            for drug_b in normalized[index + 1:]:
                pair = tuple(sorted((drug_a, drug_b)))
                if pair in known_pairs:
                    interactions.append({
                        'drugs': [drug_a, drug_b],
                        'severity': 'high',
                        'message': known_pairs[pair],
                    })

        return Response({'interactions': interactions})


class VitalSignViewSet(TenantScopedModelViewSet):
    queryset = VitalSign.objects.all()
    serializer_class = VitalSignSerializer
    permission_classes = [IsClinicalStaff]

    def get_queryset(self):
        return super().get_queryset().select_related('patient', 'recorded_by', 'visit')

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(recorded_by=user.tenant_user)


class EarlyWarningScoreViewSet(TenantScopedModelViewSet):
    queryset = EarlyWarningScore.objects.all()
    serializer_class = EarlyWarningScoreSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        return super().get_queryset().select_related('patient', 'calculated_by', 'visit')

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(calculated_by=user.tenant_user)

    @action(detail=False, methods=['post'], url_path='calculate')
    def calculate(self, request):
        """Calculate EWS from submitted vital signs without persisting."""
        data = request.data
        required = ['respiration_rate', 'oxygen_saturation', 'temperature', 'systolic_bp', 'heart_rate', 'consciousness']
        missing = [f for f in required if f not in data]
        if missing:
            return Response({'detail': f'Missing fields: {missing}'}, status=status.HTTP_400_BAD_REQUEST)
        
        result = EarlyWarningScore.calculate_newts2_score(
            respiration_rate=int(data['respiration_rate']),
            oxygen_saturation=float(data['oxygen_saturation']),
            temperature=float(data['temperature']),
            systolic_bp=int(data['systolic_bp']),
            heart_rate=int(data['heart_rate']),
            consciousness=data['consciousness']
        )
        return Response(result)


class VitalSignAlertViewSet(TenantScopedModelViewSet):
    queryset = VitalSignAlert.objects.all()
    serializer_class = VitalSignAlertSerializer
    permission_classes = [IsClinicalStaff]

    def get_queryset(self):
        queryset = super().get_queryset().select_related('patient', 'acknowledged_by', 'resolved_by')
        patient_id = self.request.query_params.get('patient')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        acknowledged = self.request.query_params.get('acknowledged')
        if acknowledged is not None:
            queryset = queryset.filter(acknowledged=acknowledged.lower() == 'true')
        resolved = self.request.query_params.get('resolved')
        if resolved is not None:
            queryset = queryset.filter(resolved=resolved.lower() == 'true')
        return queryset

    @action(detail=True, methods=['post'], url_path='acknowledge')
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        user = request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            alert.acknowledged = True
            alert.acknowledged_by = user.tenant_user
            alert.acknowledged_at = timezone.now()
            alert.save()
        return Response({'status': 'acknowledged'})

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        alert = self.get_object()
        user = request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            alert.resolved = True
            alert.resolved_by = user.tenant_user
            alert.resolved_at = timezone.now()
            alert.resolution_notes = request.data.get('resolution_notes', '')
            alert.save()
        return Response({'status': 'resolved'})

    @action(detail=False, methods=['get'], url_path='active')
    def active(self, request):
        queryset = self.get_queryset().filter(resolved=False)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ICD10CodePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class ICD10CodeViewSet(viewsets.ViewSet):
    """
    Simple ICD-10 code search endpoint.
    Returns static sample codes for common diagnoses.
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ICD10CodePagination

    SAMPLE_CODES = [
        {'code': 'A00', 'description': 'Cholera'},
        {'code': 'A01', 'description': 'Typhoid and paratyphoid fevers'},
        {'code': 'A02', 'description': 'Other salmonella infections'},
        {'code': 'A03', 'description': 'Shigellosis'},
        {'code': 'A04', 'description': 'Other bacterial intestinal infections'},
        {'code': 'A05', 'description': 'Other bacterial foodborne intoxications'},
        {'code': 'A06', 'description': 'Amebiasis'},
        {'code': 'A07', 'description': 'Other protozoal intestinal diseases'},
        {'code': 'A08', 'description': 'Viral intestinal infections'},
        {'code': 'A09', 'description': 'Infectious gastroenteritis and colitis, unspecified'},
        {'code': 'A15', 'description': 'Respiratory tuberculosis, bacteriologically confirmed'},
        {'code': 'A16', 'description': 'Respiratory tuberculosis, not confirmed bacteriologically'},
        {'code': 'A17', 'description': 'Tuberculosis of nervous system'},
        {'code': 'A18', 'description': 'Tuberculosis of other organs'},
        {'code': 'A19', 'description': 'Miliary tuberculosis'},
        {'code': 'B00', 'description': 'Herpesviral [herpes simplex] infections'},
        {'code': 'B01', 'description': 'Varicella [chickenpox]'},
        {'code': 'B02', 'description': 'Zoster [herpes zoster]'},
        {'code': 'B03', 'description': 'Smallpox'},
        {'code': 'B04', 'description': 'Monkeypox'},
        {'code': 'B05', 'description': 'Measles'},
        {'code': 'B06', 'description': 'Rubella'},
        {'code': 'B07', 'description': 'Viral warts'},
        {'code': 'B08', 'description': 'Other viral infections characterized by skin and mucous membrane lesions'},
        {'code': 'B09', 'description': 'Viral infection, unspecified'},
        {'code': 'C00', 'description': 'Malignant neoplasm of lip'},
        {'code': 'C15', 'description': 'Malignant neoplasm of esophagus'},
        {'code': 'C16', 'description': 'Malignant neoplasm of stomach'},
        {'code': 'C18', 'description': 'Malignant neoplasm of colon'},
        {'code': 'C19', 'description': 'Malignant neoplasm of rectosigmoid junction'},
        {'code': 'C20', 'description': 'Malignant neoplasm of rectum'},
        {'code': 'C22', 'description': 'Malignant neoplasm of liver and intrahepatic bile ducts'},
        {'code': 'C25', 'description': 'Malignant neoplasm of pancreas'},
        {'code': 'C34', 'description': 'Malignant neoplasm of bronchus and lung'},
        {'code': 'C43', 'description': 'Malignant melanoma of skin'},
        {'code': 'C44', 'description': 'Other malignant neoplasms of skin'},
        {'code': 'C50', 'description': 'Malignant neoplasm of breast'},
        {'code': 'C61', 'description': 'Malignant neoplasm of prostate'},
        {'code': 'C67', 'description': 'Malignant neoplasm of bladder'},
        {'code': 'D50', 'description': 'Iron deficiency anemia'},
        {'code': 'E10', 'description': 'Type 1 diabetes mellitus'},
        {'code': 'E11', 'description': 'Type 2 diabetes mellitus'},
        {'code': 'E14', 'description': 'Unspecified diabetes mellitus'},
        {'code': 'F00', 'description': 'Dementia in Alzheimer disease'},
        {'code': 'F01', 'description': 'Vascular dementia'},
        {'code': 'F03', 'description': 'Unspecified dementia'},
        {'code': 'F10', 'description': 'Mental and behavioral disorders due to use of alcohol'},
        {'code': 'F20', 'description': 'Schizophrenia'},
        {'code': 'F31', 'description': 'Bipolar disorder'},
        {'code': 'F32', 'description': 'Major depressive disorder, single episode'},
        {'code': 'F33', 'description': 'Major depressive disorder, recurrent'},
        {'code': 'G40', 'description': 'Epilepsy'},
        {'code': 'G43', 'description': 'Migraine'},
        {'code': 'G44', 'description': 'Other headache syndromes'},
        {'code': 'G47', 'description': 'Sleep disorders'},
        {'code': 'H10', 'description': 'Conjunctivitis'},
        {'code': 'H25', 'description': 'Cataract'},
        {'code': 'H40', 'description': 'Glaucoma'},
        {'code': 'H66', 'description': 'Suppurative otitis media'},
        {'code': 'I10', 'description': 'Essential hypertension'},
        {'code': 'I11', 'description': 'Hypertensive heart disease'},
        {'code': 'I20', 'description': 'Angina pectoris'},
        {'code': 'I21', 'description': 'Acute myocardial infarction'},
        {'code': 'I25', 'description': 'Chronic ischemic heart disease'},
        {'code': 'I50', 'description': 'Heart failure'},
        {'code': 'I63', 'description': 'Cerebral infarction'},
        {'code': 'J00', 'description': 'Acute nasopharyngitis [common cold]'},
        {'code': 'J01', 'description': 'Acute sinusitis'},
        {'code': 'J02', 'description': 'Acute pharyngitis'},
        {'code': 'J03', 'description': 'Acute tonsillitis'},
        {'code': 'J04', 'description': 'Acute laryngitis and tracheitis'},
        {'code': 'J05', 'description': 'Acute obstructive laryngitis [croup]'},
        {'code': 'J06', 'description': 'Acute upper respiratory infections of multiple and unspecified sites'},
        {'code': 'J10', 'description': 'Influenza due to identified influenza virus'},
        {'code': 'J11', 'description': 'Influenza, virus not identified'},
        {'code': 'J12', 'description': 'Viral pneumonia'},
        {'code': 'J13', 'description': 'Pneumonia due to Streptococcus pneumoniae'},
        {'code': 'J14', 'description': 'Pneumonia due to Haemophilus influenzae'},
        {'code': 'J15', 'description': 'Bacterial pneumonia'},
        {'code': 'J18', 'description': 'Pneumonia, unspecified'},
        {'code': 'J20', 'description': 'Acute bronchitis'},
        {'code': 'J21', 'description': 'Acute bronchiolitis'},
        {'code': 'J22', 'description': 'Acute lower respiratory infection, unspecified'},
        {'code': 'J40', 'description': 'Bronchitis, not specified as acute or chronic'},
        {'code': 'J41', 'description': 'Simple and mucopurulent chronic bronchitis'},
        {'code': 'J42', 'description': 'Unspecified chronic bronchitis'},
        {'code': 'J44', 'description': 'Other chronic obstructive pulmonary disease'},
        {'code': 'J45', 'description': 'Asthma'},
        {'code': 'J46', 'description': 'Status asthmaticus'},
        {'code': 'J47', 'description': 'Bronchiectasis'},
        {'code': 'J81', 'description': 'Pulmonary edema'},
        {'code': 'J84', 'description': 'Other interstitial pulmonary diseases'},
        {'code': 'J90', 'description': 'Pleural effusion, not elsewhere classified'},
        {'code': 'J91', 'description': 'Pleural effusion in diseases classified elsewhere'},
        {'code': 'J93', 'description': 'Pneumothorax'},
        {'code': 'J94', 'description': 'Other pleural conditions'},
        {'code': 'J95', 'description': 'Postprocedural respiratory disorders'},
        {'code': 'J96', 'description': 'Respiratory failure, not elsewhere classified'},
        {'code': 'J98', 'description': 'Other respiratory disorders'},
        {'code': 'J99', 'description': 'Respiratory disorders in diseases classified elsewhere'},
        {'code': 'K00', 'description': 'Disorders of tooth development and eruption'},
        {'code': 'K01', 'description': 'Embedded and impacted teeth'},
        {'code': 'K02', 'description': 'Dental caries'},
        {'code': 'K03', 'description': 'Other diseases of hard tissues of teeth'},
        {'code': 'K04', 'description': 'Diseases of pulp and periapical tissues'},
        {'code': 'K05', 'description': 'Gingivitis and periodontal disease'},
        {'code': 'K06', 'description': 'Other disorders of gingiva and edentulous alveolar ridge'},
        {'code': 'K07', 'description': 'Dentofacial anomalies [including malocclusion]'},
        {'code': 'K08', 'description': 'Other disorders of teeth and supporting structures'},
        {'code': 'K09', 'description': 'Cysts of oral region, not elsewhere classified'},
        {'code': 'K10', 'description': 'Other diseases of jaws'},
        {'code': 'K11', 'description': 'Diseases of salivary glands'},
        {'code': 'K12', 'description': 'Stomatitis and related lesions'},
        {'code': 'K13', 'description': 'Other diseases of lip and oral mucosa'},
        {'code': 'K14', 'description': 'Diseases of tongue'},
        {'code': 'K20', 'description': 'Esophagitis'},
        {'code': 'K21', 'description': 'Gastro-esophageal reflux disease'},
        {'code': 'K22', 'description': 'Other diseases of esophagus'},
        {'code': 'K23', 'description': 'Disorders of esophagus in diseases classified elsewhere'},
        {'code': 'K25', 'description': 'Gastric ulcer'},
        {'code': 'K26', 'description': 'Duodenal ulcer'},
        {'code': 'K27', 'description': 'Peptic ulcer, site unspecified'},
        {'code': 'K28', 'description': 'Gastrojejunal ulcer'},
        {'code': 'K29', 'description': 'Gastritis and duodenitis'},
        {'code': 'K30', 'description': 'Functional dyspepsia'},
        {'code': 'K31', 'description': 'Other functional gastric disorders'},
        {'code': 'K35', 'description': 'Acute appendicitis'},
        {'code': 'K36', 'description': 'Other appendicitis'},
        {'code': 'K37', 'description': 'Unspecified appendicitis'},
        {'code': 'K38', 'description': 'Other diseases of appendix'},
        {'code': 'K40', 'description': 'Inguinal hernia'},
        {'code': 'K41', 'description': 'Femoral hernia'},
        {'code': 'K42', 'description': 'Umbilical hernia'},
        {'code': 'K43', 'description': 'Ventral hernia'},
        {'code': 'K44', 'description': 'Diaphragmatic hernia'},
        {'code': 'K45', 'description': 'Other abdominal hernia'},
        {'code': 'K46', 'description': 'Unspecified abdominal hernia'},
        {'code': 'K50', 'description': "Crohn's disease"},
        {'code': 'K51', 'description': 'Ulcerative colitis'},
        {'code': 'K52', 'description': 'Other noninfectious gastroenteritis and colitis'},
        {'code': 'K55', 'description': 'Vascular disorders of intestine'},
        {'code': 'K56', 'description': 'Paralytic ileus and intestinal obstruction without hernia'},
        {'code': 'K57', 'description': 'Diverticular disease of intestine'},
        {'code': 'K58', 'description': 'Irritable bowel syndrome'},
        {'code': 'K59', 'description': 'Other functional intestinal disorders'},
        {'code': 'K60', 'description': 'Fisease of anal canal'},
        {'code': 'K61', 'description': 'Abscess of anal and rectal regions'},
        {'code': 'K62', 'description': 'Other diseases of anus and rectum'},
        {'code': 'K63', 'description': 'Other diseases of intestine'},
        {'code': 'K64', 'description': 'Hemorrhoids'},
        {'code': 'K65', 'description': 'Peritonitis'},
        {'code': 'K66', 'description': 'Other disorders of peritoneum'},
        {'code': 'K70', 'description': 'Alcoholic liver disease'},
        {'code': 'K71', 'description': 'Toxic liver disease'},
        {'code': 'K74', 'description': 'Fibrosis and cirrhosis of liver'},
        {'code': 'K75', 'description': 'Other inflammatory liver diseases'},
        {'code': 'K60', 'description': 'Fisease of anal canal'},
        {'code': 'K61', 'description': 'Abscess of anal and rectal regions'},
        {'code': 'K62', 'description': 'Other diseases of anus and rectum'},
        {'code': 'K63', 'description': 'Other diseases of intestine'},
        {'code': 'K64', 'description': 'Hemorrhoids'},
        {'code': 'K65', 'description': 'Peritonitis'},
        {'code': 'K66', 'description': 'Other disorders of peritoneum'},
        {'code': 'K70', 'description': 'Alcoholic liver disease'},
        {'code': 'K71', 'description': 'Toxic liver disease'},
        {'code': 'K74', 'description': 'Fibrosis and cirrhosis of liver'},
        {'code': 'K75', 'description': 'Other inflammatory liver diseases'},
        {'code': 'K80', 'description': 'Cholelithiasis'},
        {'code': 'K81', 'description': 'Cholecystitis'},
        {'code': 'K82', 'description': 'Other diseases of gallbladder'},
        {'code': 'K83', 'description': 'Other diseases of biliary tract'},
        {'code': 'K85', 'description': 'Acute pancreatitis'},
        {'code': 'K86', 'description': 'Other diseases of pancreas'},
        {'code': 'K87', 'description': 'Disorders of gallbladder, biliary tract and pancreas'},
        {'code': 'K90', 'description': 'Malabsorption syndromes'},
        {'code': 'K91', 'description': 'Intestinal complications'},
        {'code': 'K92', 'description': 'Other diseases of digestive system'},
        {'code': 'K93', 'description': 'Other diseases of digestive system'},
        {'code': 'L00', 'description': 'Bullous disorders'},
        {'code': 'L01', 'description': 'Impetigo'},
        {'code': 'L02', 'description': 'Cutaneous abscess'},
        {'code': 'L03', 'description': 'Cellulitis'},
        {'code': 'L04', 'description': 'Acute lymphadenitis'},
        {'code': 'L05', 'description': 'Pilonidal cyst'},
        {'code': 'L08', 'description': 'Other local infections of skin and subcutaneous tissue'},
        {'code': 'L10', 'description': 'Bullous disorders'},
        {'code': 'L20', 'description': 'Atopic dermatitis'},
        {'code': 'L21', 'description': 'Seborrheic dermatitis'},
        {'code': 'L22', 'description': 'Diaper dermatitis'},
        {'code': 'L23', 'description': 'Allergic contact dermatitis'},
        {'code': 'L24', 'description': 'Simple contact dermatitis'},
        {'code': 'L25', 'description': 'Unspecified contact dermatitis'},
        {'code': 'L30', 'description': 'Other dermatitis'},
        {'code': 'L40', 'description': 'Psoriasis'},
        {'code': 'L50', 'description': 'Urticaria'},
        {'code': 'L60', 'description': 'Nail disorders'},
        {'code': 'M00', 'description': 'Pyogenic arthritis'},
        {'code': 'M01', 'description': 'Direct infection of joint in infectious diseases classified elsewhere'},
        {'code': 'M02', 'description': 'Reactive arthropathies'},
        {'code': 'M03', 'description': 'Postinfective and reactive arthropathies'},
        {'code': 'M04', 'description': 'Other arthropathies'},
        {'code': 'M05', 'description': 'Rheumatoid arthritis'},
        {'code': 'M06', 'description': 'Other rheumatoid arthritis'},
        {'code': 'M10', 'description': 'Gout'},
        {'code': 'M11', 'description': 'Other crystal arthropathies'},
        {'code': 'M32', 'description': 'Systemic lupus erythematosus'},
        {'code': 'M45', 'description': 'Ankylosing spondylitis'},
        {'code': 'M50', 'description': 'Cervical disc disorder'},
        {'code': 'M51', 'description': 'Other disc disorder'},
        {'code': 'M54', 'description': 'Dorsalgia'},
        {'code': 'M79', 'description': 'Other soft tissue disorders'},
        {'code': 'M80', 'description': 'Postmenopausal osteoporosis'},
        {'code': 'M81', 'description': 'Other osteoporosis'},
        {'code': 'M82', 'description': 'Osteoporosis in diseases classified elsewhere'},
        {'code': 'N00', 'description': 'Acute nephritic syndrome'},
        {'code': 'N01', 'description': 'Rapidly progressing nephritis'},
        {'code': 'N02', 'description': 'Benign and unstable nephritis'},
        {'code': 'N03', 'description': 'Chronic nephritis syndrome'},
        {'code': 'N04', 'description': 'Nephrotic syndrome'},
        {'code': 'N05', 'description': 'Unspecified nephritic syndrome'},
        {'code': 'N06', 'description': 'Other isolated proteinuria'},
        {'code': 'N07', 'description': 'Hereditary nephritis'},
        {'code': 'N08', 'description': 'Glomerular diseases in diseases classified elsewhere'},
        {'code': 'N09', 'description': 'Glomerular disease, unspecified'},
        {'code': 'N10', 'description': 'Acute tubulointerstitial nephritis'},
        {'code': 'N11', 'description': 'Chronic tubulointerstitial nephritis'},
        {'code': 'N12', 'description': 'Tubulointerstitial nephritis, unspecified'},
        {'code': 'N13', 'description': 'Obstructive and reflux uropathy'},
        {'code': 'N14', 'description': 'Drug- and heavy-metal-induced tubulointerstitial and tubular conditions'},
        {'code': 'N15', 'description': 'Other renal tubulointerstitial diseases'},
        {'code': 'N16', 'description': 'Renal tubulointerstitial diseases in diseases classified elsewhere'},
        {'code': 'N17', 'description': 'Acute kidney failure'},
        {'code': 'N18', 'description': 'Chronic kidney disease'},
        {'code': 'N19', 'description': 'Unspecified kidney failure'},
        {'code': 'N20', 'description': 'Calculus of kidney and ureter'},
        {'code': 'N39', 'description': 'Other disorders of urinary system'},
        {'code': 'O00', 'description': 'Ectopic pregnancy'},
        {'code': 'O01', 'description': 'Hydatidiform mole'},
        {'code': 'N02', 'description': 'Benign and unstable nephritis'},
        {'code': 'N03', 'description': 'Chronic nephritis syndrome'},
        {'code': 'N04', 'description': 'Nephrotic syndrome'},
        {'code': 'N05', 'description': 'Unspecified nephritic syndrome'},
        {'code': 'N06', 'description': 'Other isolated proteinuria'},
        {'code': 'N07', 'description': 'Hereditary nephritis'},
        {'code': 'N08', 'description': 'Glomerular diseases in diseases classified elsewhere'},
        {'code': 'N10', 'description': 'Acute tubulointerstitial nephritis'},
        {'code': 'N11', 'description': 'Chronic tubulointerstitial nephritis'},
        {'code': 'N12', 'description': 'Tubulointerstitial nephritis, unspecified'},
        {'code': 'N13', 'description': 'Obstructive and reflux uropathy'},
        {'code': 'N14', 'description': 'Induced tubulointerstitial and tubular conditions'},
        {'code': 'N15', 'description': 'Other renal tubulointerstitial diseases'},
        {'code': 'N16', 'description': 'Renal tubulointerstitial diseases in diseases classified elsewhere'},
        {'code': 'N17', 'description': 'Acute kidney failure'},
        {'code': 'N18', 'description': 'Chronic kidney disease'},
        {'code': 'N19', 'description': 'Unspecified kidney failure'},
        {'code': 'N20', 'description': 'Calculus of kidney and ureter'},
        {'code': 'N39', 'description': 'Other disorders of urinary system'},
        {'code': 'O00', 'description': 'Ectopic pregnancy'},
        {'code': 'O01', 'description': 'Hydatidiform mole'},
        {'code': 'O02', 'description': 'Other abnormal products of conception'},
        {'code': 'O03', 'description': 'Complications following abortion'},
        {'code': 'O04', 'description': 'Complications following abortion'},
        {'code': 'O05', 'description': 'Complications following abortion'},
        {'code': 'O06', 'description': 'Unspecified complication following abortion'},
        {'code': 'O07', 'description': 'Failed attempted abortion'},
        {'code': 'O08', 'description': 'Complications following abortion'},
        {'code': 'O09', 'description': 'Supervision of high-risk pregnancy'},
        {'code': 'O10', 'description': 'Pre-existing diabetes mellitus in pregnancy'},
        {'code': 'O11', 'description': 'Pre-existing hypertension in pregnancy'},
        {'code': 'O12', 'description': 'Gestational hypertension'},
        {'code': 'O13', 'description': 'Gestational hypertension'},
        {'code': 'O14', 'description': 'Gestational hypertension'},
        {'code': 'O15', 'description': 'Eclampsia'},
        {'code': 'O16', 'description': 'Unspecified maternal hypertension'},
        {'code': 'O20', 'description': 'Antepartum hemorrhage'},
        {'code': 'O21', 'description': 'Excessive vomiting in pregnancy'},
        {'code': 'O22', 'description': 'Venous complications in pregnancy'},
        {'code': 'O23', 'description': 'Infections in pregnancy'},
        {'code': 'O24', 'description': 'Diabetes mellitus in pregnancy'},
        {'code': 'O25', 'description': 'Long gestation'},
        {'code': 'O26', 'description': 'Other complications of pregnancy'},
        {'code': 'O27', 'description': 'Complications of pregnancy'},
        {'code': 'O28', 'description': 'Abnormal findings on antenatal screening'},
        {'code': 'O29', 'description': 'Complications of anesthesia during pregnancy'},
        {'code': 'O30', 'description': 'Multiple gestation'},
        {'code': 'O31', 'description': 'Complications specific to multiple gestation'},
        {'code': 'O32', 'description': 'Maternal care for known or suspected fetal abnormality'},
        {'code': 'O33', 'description': 'Maternal care for known or suspected fetal abnormality'},
        {'code': 'O34', 'description': 'Maternal care for known or suspected fetal abnormality'},
        {'code': 'O35', 'description': 'Maternal care for known or suspected fetal abnormality'},
        {'code': 'O36', 'description': 'Maternal care for known or suspected fetal abnormality'},
        {'code': 'O37', 'description': 'Maternal care for known or suspected fetal abnormality'},
        {'code': 'O38', 'description': 'Maternal care for known or suspected fetal abnormality'},
        {'code': 'O39', 'description': 'Maternal care for known or suspected fetal abnormality'},
        {'code': 'O40', 'description': 'Abnormality of labor'},
        {'code': 'O41', 'description': 'Abnormality of labor'},
        {'code': 'O42', 'description': 'Abnormality of labor'},
        {'code': 'O43', 'description': 'Abnormality of labor'},
        {'code': 'O44', 'description': 'Abnormality of labor'},
        {'code': 'O45', 'description': 'Abnormality of labor'},
        {'code': 'O46', 'description': 'Abnormality of labor'},
        {'code': 'O47', 'description': 'Abnormality of labor'},
        {'code': 'O48', 'description': 'Abnormality of labor'},
        {'code': 'O49', 'description': 'Abnormality of labor'},
        {'code': 'O60', 'description': 'False labor'},
        {'code': 'O61', 'description': 'Failed induction of labor'},
        {'code': 'O62', 'description': 'Abnormalities of labor'},
        {'code': 'O63', 'description': 'Long labor'},
        {'code': 'O64', 'description': 'Obstructed labor'},
        {'code': 'O65', 'description': 'Other abnormalities of labor'},
        {'code': 'O66', 'description': 'Other abnormalities of labor'},
        {'code': 'O67', 'description': 'Other abnormalities of labor'},
        {'code': 'O68', 'description': 'Other abnormalities of labor'},
        {'code': 'O69', 'description': 'Other abnormalities of labor'},
        {'code': 'O70', 'description': 'Postpartum complications'},
        {'code': 'O71', 'description': 'Postpartum complications'},
        {'code': 'O72', 'description': 'Postpartum hemorrhage'},
        {'code': 'O73', 'description': 'Other postpartum complications'},
        {'code': 'O74', 'description': 'Other postpartum complications'},
        {'code': 'O75', 'description': 'Other complications of labor and delivery'},
        {'code': 'O80', 'description': 'Single spontaneous delivery'},
        {'code': 'O81', 'description': 'Single delivery by forceps'},
        {'code': 'O82', 'description': 'Single delivery by vacuum extractor'},
        {'code': 'O83', 'description': 'Other single delivery'},
        {'code': 'O84', 'description': 'Multiple delivery'},
        {'code': 'O85', 'description': 'Puerperal infection'},
        {'code': 'O86', 'description': 'Other puerperal complications'},
        {'code': 'O87', 'description': 'Complications of postpartum period'},
        {'code': 'O88', 'description': 'Obstetric embolism'},
        {'code': 'O89', 'description': 'Complications of anesthesia during labor and delivery'},
        {'code': 'O90', 'description': 'Complications of the puerperium'},
        {'code': 'O91', 'description': 'Infections of the genital tract'},
        {'code': 'O92', 'description': 'Other complications of the puerperium'},
        {'code': 'O98', 'description': 'Other maternal diseases'},
        {'code': 'O99', 'description': 'Other maternal diseases'},
        {'code': 'P00', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P01', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P02', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P03', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P04', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P05', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P06', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P07', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P08', 'description': 'Fetus and newborn affected by newborn conditions'},
        {'code': 'P09', 'description': 'Fetus and newborn affected by newborn conditions'},
        {'code': 'P10', 'description': 'Birth injury'},
        {'code': 'P11', 'description': 'Birth injury'},
        {'code': 'P12', 'description': 'Birth injury'},
        {'code': 'P13', 'description': 'Birth injury'},
        {'code': 'P14', 'description': 'Birth injury'},
        {'code': 'P15', 'description': 'Birth injury'},
        {'code': 'P16', 'description': 'Birth injury'},
        {'code': 'P17', 'description': 'Birth injury'},
        {'code': 'P18', 'description': 'Birth injury'},
        {'code': 'P19', 'description': 'Birth injury'},
        {'code': 'P20', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P21', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P22', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P23', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P24', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P25', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P26', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P27', 'description': 'Fetus and newborn affected by newborn conditions'},
        {'code': 'P28', 'description': 'Fetus and newborn affected by newborn conditions'},
        {'code': 'P29', 'description': 'Fetus and newborn affected by newborn conditions'},
        {'code': 'P35', 'description': 'Congenital infections'},
        {'code': 'P36', 'description': 'Congenital infections'},
        {'code': 'P37', 'description': 'Congenital infections'},
        {'code': 'P38', 'description': 'Congenital infections'},
        {'code': 'P39', 'description': 'Congenital infections'},
        {'code': 'P50', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P51', 'description': 'Fetus and newborn affected by maternal conditions'},
        {'code': 'P52', 'description': 'Fetus and newborn affected by maternal conditions'},
    ]

    def list(self, request):
        query = request.query_params.get('search', '').strip().lower()
        results = self.SAMPLE_CODES
        if query:
            results = [
                item for item in results
                if query in item['code'].lower() or query in item['description'].lower()
            ]
        return Response(results)

    def retrieve(self, request, pk=None):
        results = self.SAMPLE_CODES
        item = next((code for code in results if code['code'].lower() == pk.lower()), None)
        if not item:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(item)
