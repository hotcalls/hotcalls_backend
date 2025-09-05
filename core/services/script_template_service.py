"""
Script Template Rendering Service

This service handles dynamic Jinja2 template rendering for agent script templates.
It merges lead core fields (name, surname, email, phone) with custom variables
from the lead.variables JSONField to create a comprehensive template context.
"""
import logging
from typing import Dict, Any, Optional
from jinja2 import Environment, Template, TemplateSyntaxError, UndefinedError, StrictUndefined
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

logger = logging.getLogger(__name__)


class ScriptTemplateService:
    """
    Service for rendering agent script templates with lead data using Jinja2.
    
    Features:
    - Secure sandboxed Jinja2 environment to prevent code injection
    - Merges lead core fields with custom variables
    - Graceful error handling with fallback to original template
    - Comprehensive logging for debugging
    """
    
    def __init__(self):
        """Initialize the sandboxed Jinja2 environment."""
        # Use SandboxedEnvironment for security - prevents code execution
        self.jinja_env = SandboxedEnvironment(
            # Configure for security and usability
            autoescape=False,  # Don't HTML-escape since this is for voice scripts
            undefined=StrictUndefined,  # Raise errors for undefined variables (we'll catch them)
            trim_blocks=True,    # Clean up template formatting
            lstrip_blocks=True,  # Clean up template formatting
        )
    
    def render_script_template(
        self, 
        script_template: str, 
        lead_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Render a script template with lead data using Jinja2.
        
        Args:
            script_template (str): The Jinja2 template string from agent.script_template
            lead_data (dict, optional): Lead context data. If None, returns original template.
            
        Returns:
            str: Rendered template string, or original template on error
            
        Example:
            >>> service = ScriptTemplateService()
            >>> template = "Hello {{ name }}! Your email is {{ email }}."
            >>> context = {"name": "John", "email": "john@example.com", "budget": "5000"}
            >>> result = service.render_script_template(template, context)
            >>> print(result)  # "Hello John! Your email is john@example.com."
        """
        if not script_template or not isinstance(script_template, str):
            logger.warning("Empty or invalid script_template provided")
            return script_template or ""
        
        # If no lead data, return original template
        if not lead_data:
            logger.debug("No lead data provided, returning original template")
            return script_template
        
        try:
            # Compile the template
            template = self.jinja_env.from_string(script_template)
            
            # Render with lead context
            rendered = template.render(**lead_data)
            
            logger.info(
                "Script template rendered successfully",
                extra={
                    "template_length": len(script_template),
                    "rendered_length": len(rendered),
                    "context_keys": list(lead_data.keys()),
                    "template_preview": script_template[:100] + "..." if len(script_template) > 100 else script_template
                }
            )
            
            return rendered
            
        except TemplateSyntaxError as e:
            logger.error(
                "Jinja2 template syntax error",
                extra={
                    "error": str(e),
                    "template": script_template,
                    "line": e.lineno,
                    "context_keys": list(lead_data.keys()) if lead_data else []
                }
            )
            return script_template  # Fallback to original
            
        except (UndefinedError, SecurityError) as e:
            logger.error(
                "Template rendering error",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "template_preview": script_template[:200],
                    "context_keys": list(lead_data.keys()) if lead_data else []
                }
            )
            return script_template  # Fallback to original
            
        except Exception as e:
            logger.error(
                "Unexpected error during template rendering",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "template_length": len(script_template),
                    "context_keys": list(lead_data.keys()) if lead_data else []
                },
                exc_info=True
            )
            return script_template  # Fallback to original
    
    def merge_lead_context(self, lead) -> Dict[str, Any]:
        """
        Create template context by merging lead core fields with custom variables.
        
        Args:
            lead: Lead model instance
            
        Returns:
            dict: Merged context with core fields + custom variables
            
        Context structure:
            {
                # Core Lead model fields
                "name": "John",
                "surname": "Doe", 
                "email": "john@example.com",
                "phone": "+49123456789",
                
                # Custom variables from lead.variables JSONField
                "budget": "5000",
                "company": "ACME Corp",
                "interest": "Enterprise Plan"
            }
        """
        if not lead:
            logger.warning("No lead provided to merge_lead_context")
            return {}
        
        try:
            # Start with core Lead model fields
            context = {
                "name": getattr(lead, 'name', '') or '',
                "surname": getattr(lead, 'surname', '') or '',
                "email": getattr(lead, 'email', '') or '',
                "phone": getattr(lead, 'phone', '') or '',
            }
            
            # Merge custom variables from lead.variables JSONField
            custom_variables = getattr(lead, 'variables', {}) or {}
            if isinstance(custom_variables, dict):
                context.update(custom_variables)
            else:
                logger.warning(
                    "lead.variables is not a dict",
                    extra={
                        "lead_id": getattr(lead, 'id', None),
                        "variables_type": type(custom_variables).__name__,
                        "variables_value": custom_variables
                    }
                )
            
            logger.debug(
                "Lead context merged successfully",
                extra={
                    "lead_id": getattr(lead, 'id', None),
                    "core_fields": {k: bool(v) for k, v in context.items() if k in ['name', 'surname', 'email', 'phone']},
                    "custom_variables_count": len(custom_variables) if isinstance(custom_variables, dict) else 0,
                    "total_context_keys": len(context)
                }
            )
            
            return context
            
        except Exception as e:
            logger.error(
                "Error merging lead context",
                extra={
                    "lead_id": getattr(lead, 'id', None) if lead else None,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            # Return minimal context on error
            return {
                "name": getattr(lead, 'name', '') if lead else '',
                "surname": getattr(lead, 'surname', '') if lead else '',
                "email": getattr(lead, 'email', '') if lead else '',
                "phone": getattr(lead, 'phone', '') if lead else '',
            }
    
    def render_script_for_lead(self, script_template: str, lead) -> str:
        """
        Convenience method that combines merge_lead_context and render_script_template.
        
        Args:
            script_template (str): The Jinja2 template string
            lead: Lead model instance
            
        Returns:
            str: Rendered template or original template on error
        """
        if not lead:
            logger.debug("No lead provided, returning original template")
            return script_template or ""
        
        # Merge lead data into template context
        context = self.merge_lead_context(lead)
        
        # Render template with merged context
        return self.render_script_template(script_template, context)
    
    def render_script_for_target_ref(self, script_template: str, target_ref: str) -> str:
        """
        Unified method to render script template by resolving target_ref.
        
        This method handles both lead:<uuid> and test_user:<uuid> target references,
        providing a consistent rendering approach for all call types.
        
        Args:
            script_template (str): The Jinja2 template string
            target_ref (str): Target reference (e.g., "lead:<uuid>" or "test_user:<uuid>")
            
        Returns:
            str: Rendered template or original template on error
            
        Example:
            >>> service = ScriptTemplateService()
            >>> template = "Hello {{ name }} {{ surname }}! Your email is {{ email }}."
            >>> # For lead calls:
            >>> result = service.render_script_for_target_ref(template, "lead:123e4567-e89b-12d3-a456-426614174000")
            >>> # For test calls:
            >>> result = service.render_script_for_target_ref(template, "test_user:987fcdeb-51a2-43d6-ba89-0123456789ab")
        """
        if not script_template or not isinstance(script_template, str):
            logger.warning("Empty or invalid script_template provided")
            return script_template or ""
        
        if not target_ref:
            logger.debug("No target_ref provided, returning original template")
            return script_template
        
        try:
            # Create template context from target_ref
            context = self.create_context_from_target_ref(target_ref)
            
            # Render template with resolved context
            return self.render_script_template(script_template, context)
            
        except Exception as e:
            logger.error(
                "Error resolving target_ref for template rendering",
                extra={
                    "target_ref": target_ref,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "template_length": len(script_template)
                },
                exc_info=True
            )
            # Fallback to original template on any error
            return script_template
    
    def create_context_from_target_ref(self, target_ref: str) -> Dict[str, Any]:
        """
        Resolve target_ref to template context using resolve_call_target utility.
        
        This method provides consistent context creation for both Lead and User objects,
        ensuring template variables are mapped consistently across call types.
        
        Args:
            target_ref (str): Target reference (e.g., "lead:<uuid>" or "test_user:<uuid>")
            
        Returns:
            dict: Template context with mapped fields
            
        Context structure for lead:<uuid>:
            {
                "name": "John",
                "surname": "Doe",
                "email": "john@example.com", 
                "phone": "+49123456789",
                "budget": "5000",  # custom variables from lead.variables
                "company": "ACME Corp",
                # ... all other custom variables
            }
            
        Context structure for test_user:<uuid>:
            {
                "name": "Alice", 
                "surname": "Smith",
                "email": "alice@company.com",
                "phone": "+49987654321"
                # no custom variables for test users
            }
        """
        if not target_ref:
            logger.warning("Empty target_ref provided to create_context_from_target_ref")
            return {}
        
        try:
            # Use the existing resolve_call_target utility for consistency
            from core.utils.calltask_utils import resolve_call_target
            resolved = resolve_call_target(target_ref)
            
            # Extract the resolved objects
            lead = resolved.get('lead')
            user = resolved.get('user') 
            phone = resolved.get('phone', '')
            
            if lead is not None:
                # For lead targets, use existing lead context merging logic
                context = self.merge_lead_context(lead)
                
                logger.debug(
                    "Created context from lead target_ref",
                    extra={
                        "target_ref": target_ref,
                        "lead_id": getattr(lead, 'id', None),
                        "context_keys": list(context.keys()),
                        "custom_variables_count": len(context) - 4  # minus core fields
                    }
                )
                return context
                
            elif user is not None:
                # For test_user targets, create context from User model fields
                context = {
                    "name": getattr(user, 'first_name', '') or '',
                    "surname": getattr(user, 'last_name', '') or '',
                    "email": getattr(user, 'email', '') or '',
                    "phone": getattr(user, 'phone', '') or phone,  # fallback to resolved phone
                }
                
                logger.debug(
                    "Created context from test_user target_ref", 
                    extra={
                        "target_ref": target_ref,
                        "user_id": getattr(user, 'id', None),
                        "context_keys": list(context.keys()),
                        "has_phone": bool(context.get('phone')),
                        "has_email": bool(context.get('email')),
                        "has_name": bool(context.get('name'))
                    }
                )
                return context
                
            else:
                # Unexpected case - neither lead nor user found
                logger.warning(
                    "resolve_call_target returned neither lead nor user",
                    extra={
                        "target_ref": target_ref,
                        "resolved_keys": list(resolved.keys()),
                        "resolved_phone": phone
                    }
                )
                return {}
                
        except ValueError as e:
            # resolve_call_target raises ValueError for invalid target_ref
            logger.warning(
                "Invalid target_ref for template context",
                extra={
                    "target_ref": target_ref,
                    "error": str(e)
                }
            )
            return {}
            
        except Exception as e:
            logger.error(
                "Unexpected error creating context from target_ref",
                extra={
                    "target_ref": target_ref,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            return {}


# Global service instance for efficient reuse
script_template_service = ScriptTemplateService()