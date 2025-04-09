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

# from transformers import AutoTokenizer, AutoModelForCausalLM

# Constants
QUESTION_LOG_PATH = os.path.join(os.path.dirname(__file__), 'questionLog.csv')
PREFERRED_URLS_FILE = 'preferred_urls.txt'

# Initial message list
message_list = [
    {"role": "user",
     "content": "You are a helpful financial assistant. Always answer questions to the best of your ability."}
]




# View to return a random number as JSON
def Get_A_Number(request):
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


# View to handle appending the site's text to the message list
@csrf_exempt
def add_webtext(request):
    if request.method == 'POST':
        try:
            body_data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        text_content = body_data.get('textContent', '')
        current_url = body_data.get('currentUrl', '')

        # Basic validation
        if not text_content:
            return JsonResponse({"error": "No textContent provided."}, status=400)

        # Stored in USER role as o1-preview does not support system messages
        message_list.append({
            "role": "user",
            "content": text_content
        })

        # Debug prints
        print("[DEBUG] current_url:", current_url)
        print("[DEBUG] message_list updated:", message_list)

        return JsonResponse({"resp": "Text added successfully as user message"})
    else:
        # Graceful error handling
        return JsonResponse({'error': 'Invalid request method; use POST.'}, status=405)

# Ask button
def chat_response(request):
    question = request.GET.get('question', '')
    selected_models = request.GET.get('models', 'o1-preview,gpt-4o')
    models = selected_models.split(',')
    use_rag = request.GET.get('use_rag', 'false').lower() == 'true'

    responses = {}

    for model in models:
        if use_rag:
            # Use the RAG pipeline
            responses[model] = ds.create_rag_response(question, message_list.copy(), model)
        else:
            # Use regular response
            responses[model] = ds.create_response(question, message_list.copy(), model)

    # for model in models:
    #     if model == "gemma-2b":
    #         # Use the locally run Gemma 2B model
    #         responses[model] = ds.create_gemma_response(question, message_list.copy())
    #     else:
    #         # Use GPT-4o or other OpenAI models
    #         responses[model] = ds.create_response(question, message_list.copy(), model)

    return JsonResponse({'resp': responses})


# Advanced Ask Button
@csrf_exempt
def adv_response(request):
    question = request.GET.get('question', '')
    selected_models = request.GET.get('models', 'o1-preview,gpt-4o')
    models = selected_models.split(',')
    use_rag = request.GET.get('use_rag', 'false').lower() == 'true'

    responses = {}

    for model in models:
        if use_rag:
            # Use the RAG pipeline for advanced response
            responses[model] = ds.create_rag_advanced_response(question, message_list.copy(), model)
        else:
            # Use regular advanced response
            responses[model] = ds.create_advanced_response(question, message_list.copy(), model)

    # for model in models:
    #     if model == "gemma-2b":
    #         # Use the locally run Gemma 2B model for advanced response
    #         responses[model] = ds.create_gemma_advanced_response(question, message_list.copy())
    #     else:
    #         # Use GPT-4o or other OpenAI models for advanced response
    #         responses[model] = ds.create_advanced_response(question, message_list.copy(), model)

    return JsonResponse({'resp': responses})


# # View to handle chat responses
# def chat_response(request):
#     # Assuming 'create_response' returns a string
#     question = request.GET.get('question', '')
#     print("question is: ", question)
#     #message_list.append( {"role": "user", "content": question})
#     #print(request.body)
#     message_response = ds.create_response(question, message_list)
#     print(message_list)
#     return JsonResponse({'resp': message_response})


@csrf_exempt
def clear(request):
    print("initial message_list = " + str(message_list))
    message_list.clear()

    return JsonResponse({'resp': 'Cleared message list sucessfully' + str(message_list)})  # Return a JsonResponse


@csrf_exempt
def get_sources(request):
    query = request.GET.get('query', '')
    query = str(query)
    print(type(query))
    print("views query is ", query)
    sources = ds.get_sources(query)

    return JsonResponse({'resp': sources})  # Return a JsonResponse


@csrf_exempt
def get_logo(request):
    url = request.Get.get('url', '')

    logo_src = ds.get_website_icon(url)
    return JsonResponse({'resp', logo_src})


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
    """
    Retrieve the list of preferred URLs from the file.
    """
    if os.path.exists(PREFERRED_URLS_FILE):
        with open(PREFERRED_URLS_FILE, 'r') as file:
            urls = [line.strip() for line in file.readlines()]
    else:
        urls = []

    return JsonResponse({'urls': urls})


@csrf_exempt
def add_preferred_url(request):
    """
    Add a new preferred URL to the file.
    """
    if request.method == 'POST':
        new_url = request.POST.get('url')
        if new_url:
            with open(PREFERRED_URLS_FILE, 'a') as file:
                file.write(new_url + '\n')
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












