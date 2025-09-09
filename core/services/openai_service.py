import os
import logging
from typing import Optional, Dict, Any, List
import openai
from django.conf import settings

logger = logging.getLogger(__name__)


class OpenAIService:
    """
    Service for OpenAI API interactions, specifically for transcript summarization.
    """
    
    def __init__(self):
        # Get API key with fallback to environment variable
        api_key = getattr(settings, 'OPENAI_API_KEY', None) or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in Django settings or environment variables")
        
        self.client = openai.OpenAI(
            api_key=api_key
        )
        self.model = "gpt-4o-mini"  # Cost-effective model for summarization
    
    def summarize_transcript(self, transcript: List[Dict[str, Any]]) -> Optional[str]:
        """
        Summarize a call transcript using OpenAI.
        
        Args:
            transcript: List of transcript messages with role, content, timestamp
            
        Returns:
            str: Generated summary or None if failed
        """
        try:
            # Convert transcript to readable text
            transcript_text = self._format_transcript_for_summarization(transcript)
            
            if not transcript_text or len(transcript_text.strip()) < 10:
                logger.warning("Transcript too short or empty for summarization")
                return None
            
            # German prompt as specified
            system_prompt = """Du bist ein Experte im Zusammenfassen von Gesprächen anhand von Gesprächstranskripten. Fasse das folgende Gespräch in einer strukturierten und professionellen Weise zusammen. Gib die Zusammenfassung in einem Fließtext-Format aus. Gib nur die Zusammenfassung zurück, keine sonstigen Texte oder Erklärungen.
Fokussiere dich ausschließlich auf die Angaben der interessierten Person (Lead). Der Name des digitalen Assistenten oder des Unternehmens darf weder im Text noch implizit erwähnt werden. Wenn das Gespräch sehr kurz war oder keine relevanten Angaben gemacht wurden, erwähne am Anfang dass das Gespräch kurz war, fasse die Inhalte der Unterhaltung klar, professionell und neutral zusammen.
FORMULIERE DEN TEXT IN FLIESSTEXTFORMAT – KEINE AUFZÄHLUNGEN, KEINE EINLEITUNGEN ODER ABSCHLÜSSE, KEINE METATEXTE – NUR DIE REINE ZUSAMMENFASSUNG DER LEAD-AUSSAGEN IM FLIESSTEXT.

Beschränke dich dabei auf maximal 750 Zeichen."""

            user_prompt = f"Hier ist das zu analysierende Transkript:\n\n{transcript_text}"
            
            # Make API call to OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=300,
                temperature=0.3,
                timeout=30
            )
            
            summary = response.choices[0].message.content.strip()
            logger.info(f"Successfully generated summary of {len(summary)} characters")
            return summary
            
        except openai.APITimeoutError:
            logger.error("OpenAI API timeout while generating summary")
            return None
        except openai.APIError as e:
            logger.error(f"OpenAI API error while generating summary: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while generating summary: {e}")
            return None
    
    def _format_transcript_for_summarization(self, transcript: List[Dict[str, Any]]) -> str:
        """
        Convert transcript array to readable text format.
        
        Args:
            transcript: List of message objects with role, content, timestamp
            
        Returns:
            str: Formatted transcript text
        """
        if not transcript:
            return ""
        
        try:
            formatted_parts = []
            for message in transcript:
                if isinstance(message, dict):
                    role = message.get('role', 'Unknown')
                    content = message.get('content', '')
                    
                    # Map roles to German labels
                    speaker_label = "Assistent" if role == "assistant" else "Lead"
                    
                    if content and content.strip():
                        formatted_parts.append(f"{speaker_label}: {content}")
            
            return "\n".join(formatted_parts)
            
        except Exception as e:
            logger.error(f"Error formatting transcript: {e}")
            return str(transcript)