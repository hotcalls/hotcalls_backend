"""
Jambonz Webhook Views

Handles dynamic SIP authentication requests from Jambonz.
"""

import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from core.models import SIPTrunk

logger = logging.getLogger(__name__)


class JambonzSignatureAuthentication:
    """
    Authentication class for Jambonz webhook signature verification
    TODO: Implement signature verification similar to Meta webhook verification
    """
    def authenticate(self, request):
        # TODO: Implement Jambonz signature verification
        # For now, allow all requests (implement proper verification in production)
        return None


@method_decorator(csrf_exempt, name='dispatch')
class JambonzAuthView(APIView):
    """
    Dynamic SIP Authentication Webhook for Jambonz
    
    Handles Jambonz requests for SIP credentials when calls require authentication.
    """
    authentication_classes = []  # Custom authentication via signature
    permission_classes = [AllowAny]  # Public webhook endpoint
    
    def post(self, request):
        """
        Handle Jambonz dynamic authentication requests
        
        Expected request format from Jambonz:
        {
            "username": "agent_username",
            "realm": "sip_realm",
            "method": "INVITE",
            "response": "auth_hash" (optional)
        }
        """
        try:
            data = request.data
            username = data.get('username')
            realm = data.get('realm')
            method = data.get('method', 'INVITE')
            
            logger.info(f"Jambonz auth request: username={username}, realm={realm}, method={method}")
            
            if not username:
                logger.warning("Missing username in Jambonz auth request")
                return Response({"status": "fail", "message": "Missing username"}, status=400)
            
            try:
                # Look up SIP trunk by username
                sip_trunk = SIPTrunk.objects.get(sip_username=username, is_active=True)
                
                logger.info(f"Found SIP trunk for username {username}: {sip_trunk.provider_name}")
                
                # TODO: Decrypt password (implement encryption similar to existing token encryption)
                decrypted_password = sip_trunk.sip_password  # For now, assume plaintext
                
                response_data = {
                    "status": "ok",
                    "password": decrypted_password,
                    "expires": 300  # Cache for 5 minutes
                }
                
                logger.info(f"Returning credentials for {username} (expires in 300s)")
                return Response(response_data)
                
            except SIPTrunk.DoesNotExist:
                logger.warning(f"No SIP trunk found for username: {username}")
                return Response({"status": "fail", "message": "Invalid credentials"}, status=403)
                
        except Exception as e:
            logger.error(f"Error in Jambonz auth webhook: {e}")
            return Response({"status": "fail", "message": "Internal error"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def jambonz_auth_legacy(request):
    """
    Legacy function-based view for Jambonz authentication
    Keep this as fallback if needed
    """
    import json
    
    try:
        data = json.loads(request.body)
        username = data.get('username')
        
        if not username:
            return JsonResponse({"status": "fail"}, status=400)
            
        try:
            sip_trunk = SIPTrunk.objects.get(sip_username=username, is_active=True)
            return JsonResponse({
                "status": "ok",
                "password": sip_trunk.sip_password,
                "expires": 300
            })
        except SIPTrunk.DoesNotExist:
            return JsonResponse({"status": "fail"}, status=403)
            
    except Exception as e:
        logger.error(f"Error in legacy Jambonz auth: {e}")
        return JsonResponse({"status": "fail"}, status=500)
