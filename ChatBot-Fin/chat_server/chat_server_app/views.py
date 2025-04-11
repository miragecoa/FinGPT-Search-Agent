import json
import os
import csv
import random
from datetime import datetime
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from datascraper import datascraper as ds
from datascraper import create_embeddings as ce
from django.shortcuts import render
from django.http import HttpResponse

# Constants
QUESTION_LOG_PATH = os.path.join(os.path.dirname(__file__), 'questionLog.csv')
PREFERRED_URLS_FILE = 'preferred_urls.txt'

# Initial message list
message_list = [
    {"role": "user",
     "content": "You are a helpful financial assistant. Always answer questions to the best of your ability."}
]

# Helper functions
def _ensure_log_file_exists():
    """Create log file with headers if it doesn't exist, using UTF-8 encoding."""
    if not os.path.isfile(QUESTION_LOG_PATH):
        with open(QUESTION_LOG_PATH, 'w', newline='', encoding='utf-8') as log_file:
            writer = csv.writer(log_file)
            writer.writerow(['Button', 'URL', 'Question', 'Date', 'Time', 'Response_Preview'])

def _log_interaction(button_clicked, current_url, question, response=None):
    """
    Log interaction details with timestamp and response preview.
    Uses UTF-8 with `errors="replace"` to avoid decode errors for unexpected bytes.
    """
    _ensure_log_file_exists()

    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M:%S')

    # Safe-guard each field in case it contains invalid chars.
    def safe_str(s):
        # Convert to string, encode to utf-8 ignoring errors, then decode back.
        return str(s).encode('utf-8', errors='replace').decode('utf-8')

    # Only record first 50 chars of the response
    response_preview = response[:50] if response else "N/A"

    # Clean each field before writing
    button_clicked = safe_str(button_clicked)
    current_url = safe_str(current_url)
    question = safe_str(question)
    response_preview = safe_str(response_preview)

    # Check if identical question from same URL exists
    question_exists = False
    # Read using UTF-8 and replace invalid bytes
    with open(QUESTION_LOG_PATH, 'r', encoding='utf-8', errors='replace') as file:
        reader = csv.reader(file)
        next(reader, None)  # Skip header
        for row in reader:
            # Make sure row is long enough to avoid index errors
            if len(row) >= 3:
                existing_url = row[1]
                existing_question = row[2]
                # Compare with sanitized inputs
                if existing_url == current_url and existing_question == question:
                    question_exists = True
                    break

    if not question_exists:
        with open(QUESTION_LOG_PATH, 'a', newline='', encoding='utf-8', errors='replace') as log_file:
            writer = csv.writer(log_file)
            writer.writerow([button_clicked, current_url, question, date_str, time_str, response_preview])

# View functions
def Get_A_Number(request):
    """Return a random number as JSON"""
    int_response = random.randint(0, 99)
    return JsonResponse({'resp': int_response})


# Function to call the locally run Gemma 2B model
# def call_local_gemma_model(question):
#     model_path = os.path.join(os.path.dirname(__file__), 'gemma-2-2b-it')
#
#     # Load tokenizer and model for Gemma
#     tokenizer = AutoTokenizer.from_pretrained(model_path)
#     model = AutoModelForCausalLM.from_pretrained(
#         model_path,
#         device_map="auto"
#     )
#
#     # Tokenize and send the question to the model
#     input_ids = tokenizer(question, return_tensors="pt").to("cuda")  # Use CUDA
#     outputs = model.generate(**input_ids, max_length=200)
#
#     # Decode the response
#     response = tokenizer.decode(outputs[0], skip_special_tokens=True)
#
#     return response


# View to handle appending the text from FRONT-END SCRAPER to the message list
@csrf_exempt
def add_webtext(request):
    """Handle appending the site's text to the message list"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method; use POST.'}, status=405)
    
    try:
        body_data = json.loads(request.body)
        text_content = body_data.get('textContent', '')
        current_url = body_data.get('currentUrl', '')
        
        if not text_content:
            return JsonResponse({"error": "No textContent provided."}, status=400)
        
        # Store in USER role
        message_list.append({
            "role": "user",
            "content": text_content
        })
        
        # Log the action
        _log_interaction("add_webtext", current_url, f"Added web content: {text_content[:20]}...")
        
        return JsonResponse({"resp": "Text added successfully as user message"})
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

def chat_response(request):
    """Process chat response from selected models"""
    question = request.GET.get('question', '')
    selected_models = request.GET.get('models', 'o3-mini,gpt-4.5-preview')
    models = selected_models.split(',')
    use_rag = request.GET.get('use_rag', 'false').lower() == 'true'
    current_url = request.GET.get('current_url', '')
    
    responses = {}
    
    for model in models:
        if use_rag:
            # Use the RAG pipeline
            responses[model] = ds.create_rag_response(question, message_list.copy(), model)
        else:
            # Use regular response
            responses[model] = ds.create_response(question, message_list.copy(), model)
    
    # Log the interaction with response preview from first model
    first_model_response = next(iter(responses.values())) if responses else "No response"
    _log_interaction("chat", current_url, question, first_model_response)
    
    return JsonResponse({'resp': responses})

@csrf_exempt
def adv_response(request):
    """Process advanced chat response from selected models"""
    question = request.GET.get('question', '')
    selected_models = request.GET.get('models', 'o3-mini,gpt-4.5-preview')
    models = selected_models.split(',')
    use_rag = request.GET.get('use_rag', 'false').lower() == 'true'
    current_url = request.GET.get('current_url', '')
    
    responses = {}
    
    for model in models:
        if use_rag:
            # Use the RAG pipeline for advanced response
            responses[model] = ds.create_rag_advanced_response(question, message_list.copy(), model)
        else:
            # Use regular advanced response
            responses[model] = ds.create_advanced_response(question, message_list.copy(), model)
    
    # Log the interaction with response preview from first model
    first_model_response = next(iter(responses.values())) if responses else "No response"
    _log_interaction("advanced", current_url, question, first_model_response)
    
    return JsonResponse({'resp': responses})

@csrf_exempt
def clear(request):
    """Clear the message list"""
    message_list.clear()
    # Add back the initial system message
    message_list.append({
        "role": "user",
        "content": "You are a helpful financial assistant. Always answer questions to the best of your ability."
    })
    
    # Log the clear action
    current_url = request.GET.get('current_url', 'N/A')
    _log_interaction("clear", current_url, "Cleared message history")
    
    return JsonResponse({'resp': 'Message list cleared successfully'})

@csrf_exempt
def get_sources(request):
    """Get sources for a query"""
    query = request.GET.get('query', '')
    sources = ds.get_sources(query)
    
    # Log the source request
    current_url = request.GET.get('current_url', 'N/A')
    _log_interaction("sources", current_url, f"Source request: {query}")
    
    return JsonResponse({'resp': sources})

@csrf_exempt
def get_logo(request):
    """Get website logo"""
    url = request.GET.get('url', '')
    
    try:
        logo_src = ds.get_website_icon(url)
        return JsonResponse({'resp': logo_src})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# Legacy log_question function maintained for compatibility
def log_question(request):
    """Legacy question logging (redirects to enhanced logging)"""
    question = request.GET.get('question', '')
    button_clicked = request.GET.get('button', '')
    current_url = request.GET.get('current_url', '')
    
    if question and button_clicked and current_url:
        _log_interaction(button_clicked, current_url, question)
    
    return JsonResponse({'status': 'success'})

def get_preferred_urls(request):
    """Retrieve preferred URLs from file"""
    if os.path.exists(PREFERRED_URLS_FILE):
        with open(PREFERRED_URLS_FILE, 'r') as file:
            urls = [line.strip() for line in file.readlines()]
    else:
        urls = []
    
    return JsonResponse({'urls': urls})

@csrf_exempt
def add_preferred_url(request):
    """Add new preferred URL to file"""
    if request.method == 'POST':
        new_url = request.POST.get('url')
        if new_url:
            # Check if URL already exists
            if os.path.exists(PREFERRED_URLS_FILE):
                with open(PREFERRED_URLS_FILE, 'r') as file:
                    urls = [line.strip() for line in file.readlines()]
                if new_url in urls:
                    return JsonResponse({'status': 'exists'})
            
            # Add new URL
            with open(PREFERRED_URLS_FILE, 'a') as file:
                file.write(new_url + '\n')
            
            # Log the action
            _log_interaction("add_url", new_url, f"Added preferred URL: {new_url}")
            
            return JsonResponse({'status': 'success'})
    
    return JsonResponse({'status': 'failed'}, status=400)

@csrf_exempt
def folder_path(request):
    """
    Upload the folder path for the RAG.
    """
    print("[DEBUG] arrived in view with request:", request)
    if request.method == 'POST':
        try:
            # print("[DEBUG] raw body:", request.body)
            # body = json.loads(request.body)
            # print("[DEBUG] parsed JSON body:", body)
            # file_paths = body.get("filePaths",[])
            # print("[DEBUG] file_paths:", file_paths)

            # if not file_paths:
            #     return JsonResponse({'error': 'No file paths provided'}, status=400)

            # # Validate the file path exists
            # if not os.path.exists(file_paths):
            #     return JsonResponse({'error': 'File not found at path: {file_paths}'}, status=404)

            if 'json_data' not in request.FILES :
                return JsonResponse({'error': 'No JSON file received'}, status=400)
        
            file = request.FILES['json_data']
        
            # Read the JSON data from the file
            json_data = json.loads(file.read())
            # print("[DEBUG] json_data: ", json_data)

            # Create embeddings for files
            response_data, status_code = ce.upload_folder(json_data)
            print("[DEBUG] Flask API response:", response_data)
            print("[DEBUG] Response status code:", status_code)

            return JsonResponse(response_data, status=status_code)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)


# def get_goog_urls(request):

#     search_query = request.GET.get('query', '')

#     list_urls = ds.get_goog_urls(search_query)
#     return JsonResponse({'resp': list_urls})
