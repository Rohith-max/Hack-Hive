import requests
import json
from deep_translator import GoogleTranslator  # Open-source, easy-to-use translation

# Ollama API endpoint (adjust URL/port based on your Ollama setup)
OLLAMA_API_URL = "http://localhost:8080/api/generate"  # Default Ollama port, update if different

def generate_response(prompt, user_type, user_id, target_lang='en'):
    """
    Generate a response using the Mistral model via Ollama, supporting multilingual output.
    
    Args:
        prompt (str): The input prompt or message from the user.
        user_type (str): 'student' or 'teacher' to determine response context.
        user_id (str): User identifier (e.g., student phone number or teacher email).
        target_lang (str): Target language for the response ('en', 'kn', 'hi', etc.).
    
    Returns:
        str: The generated and translated response.
    """
    try:
        # Check if Ollama is running and Mistral model is available (optional pre-check)
        health_check = requests.get("http://localhost:8080", timeout=5)
        health_check.raise_for_status()

        # Prepare the payload for Ollama's Mistral model
        payload = {
            "model": "mistral",  # Use Mistral model (ensure it's available in Ollama)
            "prompt": f"User is a {user_type} with ID {user_id}.\nRespond to: {prompt}",  # Improved prompt structure with newline
            "stream": False,  # Get full response at once, not streamed
            "temperature": 0.7,  # Adjust for creativity (0.0-1.0)
            "max_tokens": 150  # Limit response length
        }

        # Send request to Ollama API with reduced timeout
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes

        # Parse the response (Ollama returns JSON with 'response' field)
        ollama_response = response.json().get('response', '')
        if not ollama_response:
            raise ValueError("No response received from Ollama")

        # Translate the response to the target language if not English
        translated_response = translate_text(ollama_response, target_lang)
        
        return translated_response

    except requests.RequestException as e:
        print(f"Error communicating with Ollama: {e}")
        status_code = e.response.status_code if e.response else None
        if status_code == 404:
            return "Error: Mistral model not found or Ollama server not running. Please ensure Ollama is active and the model is pulled."
        elif status_code == 500:
            return "Error: Ollama server error. Please check the server logs and try again."
        return f"Error: Could not generate response. Please try again later. (Details: {str(e)})"
    except json.JSONDecodeError as e:
        print(f"Error decoding Ollama response: {e}")
        return "Error: Invalid response format from Ollama. Please check the server configuration."
    except Exception as e:
        print(f"Unexpected error in generate_response: {e}")
        return f"Error: Unexpected issue occurred. (Details: {str(e)})"

def translate_text(text, target_lang):
    """
    Translate text to the target language using deep_translator.
    
    Args:
        text (str): The text to translate.
        target_lang (str): Target language code ('en', 'kn', 'hi', etc.).
    
    Returns:
        str: Translated text or original text if translation fails.
    """
    if target_lang == 'en':
        return text
    try:
        # Map language codes to deep_translator codes (e.g., 'kn' -> 'kannada', 'hi' -> 'hindi', 'en' -> 'english')
        lang_map = {'kn': 'kannada', 'hi': 'hindi', 'en': 'english'}
        if target_lang not in lang_map:
            raise ValueError(f"Language code {target_lang} not supported by deep_translator")
        translator = GoogleTranslator(source='english', target=lang_map[target_lang])
        translated = translator.translate(text)
        return translated
    except Exception as e:
        print(f"Translation error: {e}")
        return text  # Fallback to English if translation fails

if __name__ == "__main__":
    # Example usage (for testing outside Flask, without database access)
    prompt = "Hello, what is the weather today?"
    user_type = "student"
    user_id = "1234567890"
    response = generate_response(prompt, user_type, user_id, target_lang='en')
    print(f"Response: {response}")