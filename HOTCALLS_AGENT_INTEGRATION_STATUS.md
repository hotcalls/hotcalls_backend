# HotCalls Agent Integration Status

## 📊 AKTUELLER STATUS (Stand: 30.01.2025)

### ✅ **WAS FUNKTIONIERT:**
- **Custom Greeting**: Agent kann proaktive Begrüßungen aussprechen ✅
- **Call Status**: `successful_conversation` statt `hang_up_immediately` ✅  
- **Participant Metadata**: Wird korrekt übertragen und verarbeitet ✅
- **Agent Infrastructure**: LiveKit, TTS, STT funktionieren ✅

### ❌ **WAS NICHT FUNKTIONIERT:**
- **Agent Configuration**: Name, Voice ID werden nicht dynamisch gesetzt ❌
- **Lead Context**: Customer Data, Phone Number fehlen ❌
- **Job Metadata**: Backend sendet keine `ctx.job.metadata` ❌

---

## 🔧 **TECHNICAL PROBLEM**

### **Zwei Metadata-Quellen in LiveKit:**

| **Metadata Type** | **Status** | **Contains** | **Backend sends?** |
|-------------------|------------|--------------|-------------------|
| **`ctx.job.metadata`** | ❌ FEHLT | Agent Config, Voice ID, Lead Data | **NEIN** |
| **`participant.metadata`** | ✅ WORKS | Custom Greeting, Call Data | **JA** |

### **Agent erwartet BEIDE Quellen:**
```python
# 1. Job Metadata (Agent-Start-Konfiguration) - FEHLT!
if hasattr(ctx.job, 'metadata') and ctx.job.metadata:
    hotcalls_metadata = json.loads(ctx.job.metadata)
    # Agent Name, Voice ID, Lead Data

# 2. Participant Metadata (Call-spezifische Daten) - FUNKTIONIERT!
if participant.metadata:
    custom_greeting = participant.metadata.get('custom_greeting')
```

---

## 🎯 **LÖSUNG: Backend Integration**

### **Backend muss BEIDE Metadata-Quellen befüllen:**

```python
# 1. Agent Dispatch (für ctx.job.metadata)
dispatch = await livekit_api.agent_dispatch.create_dispatch(
    api.CreateAgentDispatchRequest(
        agent_name="hotcalls_agent",
        room=room_name,
        metadata=json.dumps({
            "agent_config": {
                "agent_id": "12345",
                "name": "Sarah",
                "voice_external_id": "L0yTtpRXzdyzQlzALhgD",
                "language": "de",
                "greeting_outbound": "Hallo! Hier ist Sarah..."
            },
            "customer_name": "Max Mustermann",
            "phone_number": "+49123456789",
            "call_reason": "Terminvereinbarung",
            "lead_data": {
                "company": "Beispiel GmbH",
                "address": "Musterstraße 123",
                "city": "Berlin",
                "zip_code": "12345",
                "country": "Deutschland"
            }
        })
    )
)

# 2. SIP Participant (für participant.metadata)  
sip_participant = await livekit_api.sip.create_sip_participant(
    api.CreateSIPParticipantRequest(
        sip_trunk_id=TRUNK_ID,
        sip_call_to=phone_number,
        room_name=room_name,
        participant_metadata=json.dumps({
            "custom_greeting": "Hallo! Hier ist Sarah von der Beispiel GmbH..."
        })
    )
)
```

---

## 📋 **REQUIRED FIELDS für job.metadata**

### **Agent Configuration:**
```json
{
    "agent_config": {
        "agent_id": "string",
        "name": "string (REQUIRED)",
        "voice_external_id": "string (REQUIRED - ElevenLabs ID)",
        "voice_provider": "elevenlabs",
        "language": "de|en",
        "greeting_outbound": "string",
        "character": "string",
        "prompt": "string (optional override)"
    }
}
```

### **Customer Data:**
```json
{
    "customer_name": "string",
    "phone_number": "string (E.164 format)",
    "call_reason": "string"
}
```

### **Lead Data:**
```json
{
    "lead_data": {
        "company": "string",
        "address": "string", 
        "city": "string",
        "state": "string",
        "zip_code": "string",
        "country": "string",
        "notes": "string"
    }
}
```

---

## 🚨 **CURRENT LOGS ANALYSIS**

### **❌ Missing HotCalls Logs:**
```bash
# DIESE LOGS FEHLEN KOMPLETT:
🎯 HOTCALLS metadata found in job.metadata with keys: [...]
🎭 Agent config from HotCalls: Sarah
🎤 Voice ID from HotCalls: L0yTtpRXzdyzQlzALhgD
👤 Customer from HotCalls: Max Mustermann
```

### **✅ Working Logs:**
```bash
🗣️ Delivering custom outbound greeting
📝 Agent message: Macht Party...
🕐 Greeting delivery completed at 4.94s
```

### **❌ Fallback Logs (zeigen Problem):**
```bash
📝 Agent message: Guten Morgen! Hier ist TestAgent...
# ↑ "TestAgent" kommt aus .env, nicht aus HotCalls!
```

---

## 🔄 **NEXT STEPS**

1. **Backend Team**: Implementierung der `job.metadata` Übertragung
2. **Test**: Vollständiger HotCalls-Aufruf mit allen Feldern
3. **Verification**: Logs prüfen auf HotCalls-spezifische Meldungen
4. **Production**: Agent läuft vollständig dynamisch

---

## ✅ **SUCCESS CRITERIA**

Der Agent ist **vollständig dynamisch**, wenn diese Logs erscheinen:

```bash
🎯 HOTCALLS metadata found in job.metadata with keys: [agent_config, customer_name, ...]
🎭 Agent config from HotCalls: Sarah
🎤 Using ElevenLabs voice_external_id from payload: L0yTtpRXzdyzQlzALhgD
👤 Customer from HotCalls: Max Mustermann
📞 Phone from HotCalls: +49123456789
🎯 Call reason: Terminvereinbarung
```

**Dann ist der Agent 100% dynamisch und verwendet alle HotCalls-Daten! 🚀**

---

## 📝 **BACKEND IMPLEMENTATION DETAILS**

### **Aktuelle Backend-Struktur prüfen:**

```python
# In core/utils/livekit_calls.py - PRÜFEN OB FUNKTIONIERT:

# Agent Dispatch - DIESE DATEN GEHEN AN job.metadata
dispatch = await livekit_api.agent_dispatch.create_dispatch(
    api.CreateAgentDispatchRequest(
        agent_name=agent_name,
        room=room_name,
        metadata=json.dumps(metadata)  # ← DIESE DATEN MÜSSEN ANKOMMEN!
    )
)

# SIP Participant - DIESE DATEN GEHEN AN participant.metadata  
request = CreateSIPParticipantRequest(
    sip_trunk_id=sip_trunk_id,
    sip_call_to=lead_data['phone'],
    room_name=room_name,
    participant_identity=participant_identity,
    participant_name=participant_name,
    participant_metadata=json.dumps(metadata),  # ← FUNKTIONIERT BEREITS!
)
```

### **Debug: Was sendet das Backend?**

```python
# Debug-Output im Backend zeigt:
print(f"🔍 DEBUG: Metadata being sent to agent_dispatch:")
print(f"   - agent_config: {metadata.get('agent_config', 'MISSING')}")
print(f"   - voice_external_id: {metadata.get('agent_config', {}).get('voice_external_id', 'MISSING')}")

# Agent sollte diese Logs zeigen:
🎯 HOTCALLS metadata found in job.metadata with keys: [agent_config, customer_name, lead_data, ...]
```

### **Wenn job.metadata NICHT ankommt:**

**Mögliche Ursachen:**
1. `agent_dispatch.metadata` wird nicht korrekt als `job.metadata` weitergereicht
2. Agent startet bevor Dispatch-Metadata verfügbar ist
3. LiveKit API-Version Kompatibilitätsproblem
4. JSON-Serialisierung Problem

**Debugging:**
```python
# Im Agent hinzufügen:
print(f"🔍 DEBUG: ctx.job object: {dir(ctx.job)}")
print(f"🔍 DEBUG: ctx.job.metadata exists: {hasattr(ctx.job, 'metadata')}")
print(f"🔍 DEBUG: ctx.job.metadata value: {getattr(ctx.job, 'metadata', 'NOT_FOUND')}")
```

---

## 🎯 **FAZIT**

**Current State:** 50% funktionsfähig  
**Missing:** `job.metadata` Übertragung vom Backend  
**Next Action:** Backend-Implementierung verifizieren und debuggen

Der Agent ist technisch bereit - das Backend muss nur sicherstellen, dass die `agent_dispatch.metadata` auch als `ctx.job.metadata` beim Agent ankommt! 🚀 