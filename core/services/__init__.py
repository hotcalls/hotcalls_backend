from .google_calendar import GoogleCalendarService
from .jambonz_integration import JambonzIntegrationService as JambonzService
from .meta_integration import MetaIntegrationService
try:
    from .microsoft_calendar import MicrosoftCalendarService  # noqa: F401
except Exception:
    # Allow partial deployments while Microsoft service is being rolled out
    MicrosoftCalendarService = None  # type: ignore

try:
    from .webhook_lead_service import WebhookLeadService
except Exception:  # avoid import errors during partial deploys
    WebhookLeadService = None  # type: ignore

 