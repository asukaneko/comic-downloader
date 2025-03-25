import configparser

config_parser = configparser.ConfigParser()
config_parser.read('config.ini')

MAX_HISTORY_LENGTH = 20

user_messages = {}
group_messages = {}

api_key = config_parser.get('ApiKey', 'api_key')
base_url = config_parser.get('ApiKey', 'base_url')
model = config_parser.get('ApiKey', 'model')

def load_prompt(user_id=None, group_id=None):
    prompt_file = None
    if user_id:
        user_id = str(user_id)
        prompt_file = f"prompts/user/user_{user_id}.txt"
    elif group_id:
        group_id = str(group_id)
        prompt_file = f"prompts/group/group_{group_id}.txt"

    try:
        with open(prompt_file, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        try:
            with open("neko.txt", "r", encoding="utf-8") as file:
                return file.read()
        except FileNotFoundError:
            return ""

def chat(content, user_id=None, group_id=None):
    from openai import OpenAI

    if user_id:
        user_id = str(user_id)
        if user_id not in user_messages:
            prompt = load_prompt(user_id=user_id)
            user_messages[user_id] = [{"role": "system", "content": prompt}]
        messages = user_messages[user_id]
    elif group_id:
        group_id = str(group_id)
        if group_id not in group_messages:
            prompt = load_prompt(group_id=group_id)
            group_messages[group_id] = [{"role": "system", "content": prompt}]
        messages = group_messages[group_id]
    else:
        messages = []

    messages.append({"role": "user", "content": content})

    if len(messages) > MAX_HISTORY_LENGTH:
        messages = messages[-MAX_HISTORY_LENGTH:]

    client = OpenAI(api_key=api_key,
                    base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False
    )
    assistant_response = response.choices[0].message.content
    messages.append({"role": "assistant", "content": assistant_response})
    return assistant_response
