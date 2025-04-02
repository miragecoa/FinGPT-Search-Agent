import json
import os
import csv
import random
from datetime import datetime
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from datascraper import datascraper as ds
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
    """Create log file with headers if it doesn't exist"""
    if not os.path.isfile(QUESTION_LOG_PATH):
        with open(QUESTION_LOG_PATH, 'w', newline='') as log_file:
            writer = csv.writer(log_file)
            writer.writerow(['Button', 'URL', 'Question', 'Date', 'Time', 'Response_Preview'])

def _log_interaction(button_clicked, current_url, question, response=None):
    """Log interaction details with timestamp and response preview"""
    _ensure_log_file_exists()
    
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M:%S')
    
    # Get response preview (first 50 chars) if available
    response_preview = response[:50] if response else "N/A"
    
    # Check if identical question from same URL exists
    question_exists = False
    with open(QUESTION_LOG_PATH, 'r') as file:
        reader = csv.reader(file)
        next(reader, None)  # Skip header
        for row in reader:
            if len(row) >= 3 and row[1] == current_url and row[2] == question:
                question_exists = True
                break
    
    if not question_exists:
        with open(QUESTION_LOG_PATH, 'a', newline='') as log_file:
            writer = csv.writer(log_file)
            writer.writerow([button_clicked, current_url, question, date_str, time_str, response_preview])

# View functions
def Get_A_Number(request):
    """Return a random number as JSON"""
    int_response = random.randint(0, 99)
    return JsonResponse({'resp': int_response})

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
    selected_models = request.GET.get('models', 'o1-preview,gpt-4o')
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
    selected_models = request.GET.get('models', 'o1-preview,gpt-4o')
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