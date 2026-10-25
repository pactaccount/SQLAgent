"""Single-model NVIDIA API gateway; no model weights or GPU needed by the web app."""
import os
import requests
import settings  # Loads only the project-local .env, without overriding deployment secrets.


class ModelServiceError(RuntimeError):
    def __init__(self,message,status_code=None):
        super().__init__(message)
        self.status_code=status_code


def model_config():
    return {
        'model':os.getenv('NVIDIA_MODEL','nvidia/nemotron-3.5-lightning-30b-a3b'),
        'base_url':os.getenv('NVIDIA_API_BASE','https://integrate.api.nvidia.com/v1').rstrip('/'),
    }


def complete(messages):
    config=model_config()
    key=os.getenv('NVIDIA_API_KEY','').strip()
    if not key:raise ModelServiceError('NVIDIA_API_KEY is not configured.')
    payload={'model':config['model'],'messages':messages,'temperature':0,
             'max_tokens':1536,'response_format':{'type':'json_object'},
             'extra_body':{'chat_template_kwargs':{'enable_thinking':False}}}
    # NVIDIA's direct API expects template options at the top level; extra_body is
    # an SDK convention, not part of the HTTP request schema.
    payload.update(payload.pop('extra_body'))
    try:
        response=requests.post(config['base_url']+'/chat/completions',
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},
            json=payload,timeout=(10,120))
    except requests.RequestException as error:
        raise ModelServiceError('Model provider connection failed or timed out.') from error
    if not response.ok:
        raise ModelServiceError(f'Model provider returned HTTP {response.status_code}.',response.status_code)
    try:
        result=response.json()
        text=result['choices'][0]['message']['content']
        if not isinstance(text,str) or not text.strip():raise ValueError('Empty response')
        return text,result.get('model',config['model'])
    except (ValueError,KeyError,IndexError,TypeError) as error:
        raise ModelServiceError('Model provider returned an invalid completion.') from error


def health():
    return {'configured':bool(os.getenv('NVIDIA_API_KEY')),**model_config(),
            'note':'Configuration check only; does not spend inference quota.'}
