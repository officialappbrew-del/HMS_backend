# HL7 / FHIR Integration Guide for SmartCare HMS

## Goal
Allow SmartCare HMS to exchange patient, encounter and laboratory data with external systems such as:
- Lab machines
- Hospital information systems
- Referral hospitals
- Ministry of health reporting gateways
- Third-party EMR/EHR systems

This is done using standard medical interoperability formats:
- HL7 v2 for legacy lab and device messaging
- FHIR for modern API-based exchanges

## Why this matters
The system can now receive data from external systems and push data back out without custom one-off integrations. This reduces manual work, improves patient safety, and makes it easier to connect to labs, national reporting platforms, and other hospitals.

## Recommended architecture

### 1. Interoperability layer
Create a dedicated integration app that exposes both HL7 and FHIR endpoints.

### 2. Data mapping layer
Map internal HMS records to FHIR resources and HL7 segments:
- Patient -> FHIR Patient / HL7 PID
- Lab result -> FHIR Observation / HL7 OBX
- Order -> FHIR ServiceRequest / HL7 ORC + OBR

### 3. Security layer
Use:
- OAuth2 / JWT for API clients
- mTLS for high-trust integrations
- IP allowlists for external systems
- Signed payload validation for inbound data

### 4. Audit layer
Every inbound and outbound message should be stored in the existing audit log system with:
- timestamp
- source system
- message type
- status
- payload hash or correlation ID

## Current implementation in this project
The project now includes a lightweight interoperability layer under the integration app:

- FHIR machine-readable resources
- HL7 message ingest endpoint
- Capability statement endpoint
- Patient and Observation mapping helpers

### Routes
- /api/v1/integration/fhir/
- /api/v1/integration/fhir/metadata/
- /api/v1/integration/fhir/patient/<id>/
- /api/v1/integration/hl7/message/

## Example FHIR patient payload

{
  "resourceType": "Patient",
  "id": "123",
  "identifier": [
    {"system": "https://smartcarehms.com/patient/hospital-number", "value": "LAG-2026-100123"}
  ],
  "name": [{"family": "Bello", "given": ["Grace"]}],
  "gender": "female",
  "birthDate": "1992-02-12"
}

## Example HL7 message

MSH|^~\\&|LAB|HOSP1|HMS|SMARTCARE|20260803120000||ORU^R01|MSG123|P|2.5
PID|||12345||Bello^Grace||19920212|F
OBX|1|NM|GLUCOSE^Glucose|1|120|mg/dL|70-110|H|

## What you should do next

### Phase 1: Production hardening
1. Add authentication to the integration endpoints using OAuth2 or API keys.
2. Restrict access by tenant and trusted partner.
3. Store all inbound/outbound messages in a secure message log table.
4. Add retry logic and dead-letter queue handling for failed message processing.

### Phase 2: Real system mapping
1. Map all patient demographics to FHIR Patient.
2. Map visits, admissions, diagnoses, medications, and results to FHIR resources.
3. Add support for Observation, Encounter, Condition, MedicationRequest, and DiagnosticReport.
4. Generate HL7 ACK/NACK messages for receiving systems.

### Phase 3: External lab and hospital integration
1. Connect to lab analyzers using HL7 v2 over TCP/IP or MLLP.
2. Expose a FHIR API for partner hospitals.
3. Define a queue for asynchronous message processing.
4. Add transformation pipelines that normalize different vendor payloads.

### Phase 4: Governance and compliance
1. Log every access and data transfer.
2. Enforce patient consent rules.
3. Ensure HIPAA/GDPR data minimization in all exchanged payloads.
4. Track message integrity and data provenance.

## Best practices
- Keep messages schema-driven, not free-form.
- Validate payloads before storing to the database.
- Use versioned FHIR profiles for your hospital.
- Keep transformation logic in service classes, not in views.
- Build a test suite for known lab and hospital payloads.

## Suggested next milestone
A strong first production milestone is:
- inbound FHIR Patient and Observation support
- inbound HL7 ORU message processing for laboratory results
- outbound ACK/NACK generation
- audit logging for every exchange

That gives you a real interoperability foundation without a huge implementation risk.
