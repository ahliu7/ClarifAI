import os
from typing import Dict, Any, List, Optional
from google import generativeai as genai
import json
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        # Set the API key for Google Generative AI
        genai.api_key = api_key
        # Using Gemini 2.5 Flash model
        self.model = genai.GenerativeModel('models/gemini-2.5-flash-preview-04-17')
        self.flagged_concepts: List[Dict[str, Any]] = []  # Track flagged concepts
    
    def _safe_api_call(self, prompt: str, response_schema: Dict[str, Any] = None) -> Any:
        """
        Makes a safe API call with proper configuration for JSON responses.
        
        Args:
            prompt: The prompt to send to the model
            response_schema: Optional JSON schema to structure the response
            
        Returns:
            The parsed response or None if there was an error
        """
        try:
            # Configure generation parameters to get structured JSON
            generation_config = {
                "temperature": 0.2,  # Lower temperature for more deterministic responses
                "top_p": 0.8,
                "top_k": 40,
                "response_mime_type": "application/json",  # Request JSON output
            }
            
            # Add explicit request for JSON at the end of the prompt
            json_prompt = f"{prompt}\n\nRespond with a valid JSON object only. No explanations or markdown."
            
            # Make the API call with specific generation config
            response = self.model.generate_content(
                json_prompt, 
                generation_config=generation_config
            )
            
            # Try to parse the response as JSON
            if hasattr(response, 'text'):
                try:
                    return json.loads(response.text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse response as JSON: {e}")
                    logger.error(f"Response text: {response.text[:500]}...")
                    return None
            return None
        except Exception as e:
            logger.error(f"API call error: {str(e)}")
            return None
    
    async def process_audio_transcript(self, transcript: str, previous_transcript: str = "") -> Dict[str, Any]:
        """
        Process an audio transcript using Gemini API.
        
        Args:
            transcript (str): The full text transcript from audio
            previous_transcript (str): The previous transcript (for incremental processing)
            
        Returns:
            Dict containing:
            - concepts: List of identified concepts with their locations in the text
            - current_concept: Currently discussed concept
            - new_content: True if new content was detected
            - flagged_history: History of flagged concepts
        """
        # Check if there's new content to process
        has_new_content = len(transcript) > len(previous_transcript)
        
        # If no new content, return previous concepts without processing
        if not has_new_content and hasattr(self, 'last_concepts'):
            return {
                "concepts": self.last_concepts,
                "current_concept": self.last_current_concept if hasattr(self, 'last_current_concept') else None,
                "new_content": False,
                "flagged_history": self.flagged_concepts,
                "status": "success"
            }
            
        # Define the schema for the response
        response_schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept_name": {"type": "string"},
                    "text_snippet": {"type": "string"},
                    "start_position": {"type": "integer"},
                    "end_position": {"type": "integer"},
                    "difficulty_level": {"type": "integer", "minimum": 1, "maximum": 5},
                    "is_current": {"type": "boolean"}
                },
                "required": ["concept_name", "text_snippet", "difficulty_level", "is_current"]
            }
        }
            
        # First, identify and structure the concepts from the transcript
        concepts_prompt = f"""
        You are an educational content analyzer. Analyze this lecture transcript and identify key concepts that students might find challenging.
        
        Focus on the most recent/last part of the transcript to identify what's currently being discussed.
        For each concept:
        1. Identify the concept name
        2. Extract the relevant text snippet where it's discussed
        3. Determine the start and end position of the concept in the text (0-indexed character positions)
        4. Assess potential difficulty (1-5 scale)
        5. Indicate if this is currently being discussed (true/false)

        Transcript:
        {transcript}
        
        Respond with a JSON array where each element is an object with these fields:
        - concept_name: String with the name of the concept
        - text_snippet: String with the excerpt from the transcript
        - start_position: Integer with the start position in the transcript
        - end_position: Integer with the end position in the transcript
        - difficulty_level: Integer from 1-5
        - is_current: Boolean indicating if it's being discussed now
        """
        
        # Make the API call with the schema
        concepts_data = self._safe_api_call(concepts_prompt, response_schema)
        
        # Handle invalid or empty responses
        if not concepts_data or not isinstance(concepts_data, list) or len(concepts_data) == 0:
            # Fallback to a default concept
            concepts_data = [{
                "concept_name": "Data Structures",
                "text_snippet": transcript[:100] + "...",
                "start_position": 0,
                "end_position": len(transcript),
                "difficulty_level": 3,
                "is_current": True
            }]

        # Identify current concepts being discussed
        current_concepts = [c for c in concepts_data if c.get("is_current", False)]
        current_concept = current_concepts[0] if current_concepts else (concepts_data[-1] if concepts_data else None)
        
        # Store for future reference
        self.last_concepts = concepts_data
        self.last_current_concept = current_concept

        return {
            "concepts": concepts_data,
            "current_concept": current_concept,
            "new_content": has_new_content,
            "flagged_history": self.flagged_concepts,
            "status": "success"
        }
        
    async def explain_concept(self, concept_name: str, context: str) -> Dict[str, Any]:
        """
        Generate a detailed explanation for a specific concept.
        
        Args:
            concept_name: The name of the concept to explain
            context: The relevant context from the lecture
            
        Returns:
            Dict containing the explanation and examples
        """
        # Define the schema for the explanation
        response_schema = {
            "type": "object",
            "properties": {
                "explanation": {"type": "string"},
                "examples": {"type": "array", "items": {"type": "string"}},
                "misconceptions": {"type": "array", "items": {"type": "string"}},
                "related_concepts": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["explanation", "examples", "misconceptions", "related_concepts"]
        }
        
        prompt = f"""
        You are an educational assistant helping a student understand a difficult concept.
        
        Explain the concept of "{concept_name}" in detail based on this context:
        
        {context}

        Provide:
        1. A clear, simple explanation
        2. Three concrete examples
        3. Common misconceptions
        4. Related concepts to explore
        """
        
        # Make the API call with the schema
        explanation_data = self._safe_api_call(prompt, response_schema)
        
        # Default explanation if API call fails
        default_explanation = {
            "explanation": f"The concept of {concept_name} refers to {context}",
            "examples": ["Example 1", "Example 2", "Example 3"],
            "misconceptions": ["Common misconception"],
            "related_concepts": ["Related concept"]
        }
        
        # If API call failed or didn't return correct format, use default
        if not explanation_data or not isinstance(explanation_data, dict):
            explanation_data = default_explanation
        else:
            # Ensure all required fields exist
            for field in ["explanation", "examples", "misconceptions", "related_concepts"]:
                if field not in explanation_data or not explanation_data[field]:
                    explanation_data[field] = default_explanation[field]
        
        # Add to flagged history with proper timestamp
        timestamp = datetime.now().isoformat()
        self.flagged_concepts.append({
            "concept": concept_name,
            "timestamp": timestamp,
            "context": context,
            "explanation": explanation_data
        })
        
        return {
            "explanation": explanation_data,
            "timestamp": timestamp,
            "status": "success"
        }
    
    async def evaluate_understanding(self, lecture_transcript: str, user_explanation: str) -> Dict[str, Any]:
        """
        Evaluate user's understanding based on their explanation and generate follow-up questions.
        
        Args:
            lecture_transcript: Original lecture content
            user_explanation: User's audio transcript explaining the concept
            
        Returns:
            Dict containing evaluation, feedback, and follow-up questions
        """
        # Define the schema for the evaluation
        response_schema = {
            "type": "object",
            "properties": {
                "understanding_level": {"type": "integer", "minimum": 1, "maximum": 5},
                "accurate_points": {"type": "array", "items": {"type": "string"}},
                "gaps": {"type": "array", "items": {"type": "string"}},
                "follow_up_questions": {"type": "array", "items": {"type": "string"}},
                "improvement_suggestions": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["understanding_level", "accurate_points", "gaps", "follow_up_questions", "improvement_suggestions"]
        }
        
        prompt = f"""
        You are an educational assistant evaluating a student's understanding of a concept.
        
        Compare the student's explanation with the original lecture content:

        Original Lecture:
        {lecture_transcript}

        Student's Explanation:
        {user_explanation}

        Evaluate their understanding by providing:
        1. Understanding level (1-5 scale, where 5 is excellent)
        2. Accurate points they made
        3. Misconceptions or gaps in their understanding
        4. Follow-up questions to deepen their understanding
        5. Suggestions for improvement
        """

        # Make the API call with the schema
        evaluation_data = self._safe_api_call(prompt, response_schema)
        
        # Default evaluation if API call fails
        default_evaluation = {
            "understanding_level": 3,
            "accurate_points": ["The student showed some understanding of the concept"],
            "gaps": ["Some details were missing"],
            "follow_up_questions": ["Can you elaborate more on the concept?"],
            "improvement_suggestions": ["Consider explaining with examples"]
        }
        
        # If API call failed or didn't return correct format, use default
        if not evaluation_data or not isinstance(evaluation_data, dict):
            evaluation_data = default_evaluation
        else:
            # Ensure all required fields exist
            for field in ["understanding_level", "accurate_points", "gaps", "follow_up_questions", "improvement_suggestions"]:
                if field not in evaluation_data or not evaluation_data[field]:
                    evaluation_data[field] = default_evaluation[field]
        
        return {
            "evaluation": evaluation_data,
            "status": "success"
        }
    
    async def teach_to_learn(self, topic: str, user_response: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Interactive teach-to-learn mode that evaluates user understanding and creates
        follow-up questions to improve comprehension.
        
        Args:
            topic: The main topic or concept being discussed
            user_response: The user's latest spoken response
            conversation_history: List of previous exchanges in the conversation
            
        Returns:
            Dict containing:
            - understanding_score: Integer from 0-100 representing mastery level
            - response: Text response to be spoken back to the user
            - follow_up_question: Next question to deepen understanding
            - is_complete: Boolean indicating if the learning session can conclude
        """
        # Initialize conversation history if not provided
        if conversation_history is None:
            conversation_history = []
            
        # Define the schema for the response
        response_schema = {
            "type": "object",
            "properties": {
                "understanding_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "evaluation": {"type": "string"},
                "response": {"type": "string"},
                "follow_up_question": {"type": "string"},
                "is_complete": {"type": "boolean"}
            },
            "required": ["understanding_score", "response", "follow_up_question", "is_complete"]
        }
        
        # Convert conversation history to formatted string
        conversation_text = ""
        for exchange in conversation_history:
            if "user" in exchange:
                conversation_text += f"User: {exchange['user']}\n"
            if "ai" in exchange:
                conversation_text += f"AI: {exchange['ai']}\n"
        
        # Create the prompt for teaching interaction
        prompt = f"""
        You are an expert teacher helping a student understand the concept of "{topic}".
        Your goal is to evaluate their understanding and ask questions that will help them reach mastery.
        
        Previous conversation:
        {conversation_text}
        
        Student's latest response:
        {user_response}
        
        Evaluate their current understanding of the concept on a scale from 0-100.
        Then provide:
        1. A brief evaluation of their understanding
        2. A response that addresses any misconceptions and reinforces correct understanding
        3. A follow-up question that will help deepen their understanding
        4. Whether they've reached sufficient mastery (85% or higher)
        
        Keep the response conversational, engaging, and focused on the concept.
        Don't directly tell them their score, but use it to guide your teaching approach.
        """
        
        # Make the API call with the schema
        result = self._safe_api_call(prompt, response_schema)
        
        # Handle invalid or empty responses
        if not result or not isinstance(result, dict):
            # Return a default format
            return {
                "understanding_score": 50,
                "evaluation": "I couldn't properly evaluate your response.",
                "response": "That's an interesting perspective. Let's explore this topic a bit more.",
                "follow_up_question": f"Can you explain more about how you understand {topic}?",
                "is_complete": False
            }
        
        return result
    
    async def get_flagged_history(self) -> Dict[str, Any]:
        """
        Retrieve the history of flagged concepts.
        
        Returns:
            Dict containing the history of flagged concepts
        """
        return {
            "flagged_concepts": self.flagged_concepts,
            "status": "success"
        }
    
    async def generate_organized_notes(self, transcript: str) -> Dict[str, Any]:
        """
        Generate organized notes from a raw transcript.
        
        Args:
            transcript: The raw transcript text
            
        Returns:
            Dict containing:
            - title: A title for the notes
            - content: The organized content in markdown format
            - sections: List of sections with headings and content
        """
        # Define the schema for the organized notes
        response_schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["title", "content", "sections"]
        }
            
        # Create the prompt for organizing notes
        notes_prompt = f"""
        You are an expert at organizing lecture transcriptions into clear, structured notes.
        Analyze this raw transcript and create well-organized lecture notes.
        
        Include:
        1. An appropriate title for the lecture
        2. Well-organized content with headings, bullet points, and formatting
        3. Logical sections that capture the main topics
        
        Format the content using markdown syntax for better readability.
        
        Raw Transcript:
        {transcript}
        
        Respond with a JSON object containing:
        - title: A concise title for these notes
        - content: The full formatted content in markdown
        - sections: An array of section objects with 'heading' and 'content' fields
        """
        
        # Make the API call with the schema
        notes_data = self._safe_api_call(notes_prompt, response_schema)
        
        # Handle invalid or empty responses
        if not notes_data or not isinstance(notes_data, dict):
            # Return a default format
            return {
                "title": "Lecture Notes",
                "content": transcript,
                "sections": [{
                    "heading": "Main Content",
                    "content": transcript
                }]
            }
        
        return notes_data 
        