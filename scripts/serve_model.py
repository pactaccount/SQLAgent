"""Loopback-only, serialized MLX inference service. Run in .venv-mlx."""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from settings import MODEL_PATH, ROOT
from mlx_lm import load,generate
from mlx_lm.sample_utils import make_sampler

manifest=json.loads((ROOT/'artifacts/setup/model_manifest.json').read_text())
MODEL_ID=manifest['repository']+'@'+manifest['revision']
model,tokenizer=load(str(MODEL_PATH))


class Handler(BaseHTTPRequestHandler):
    def respond(self,status,payload):
        body=json.dumps(payload).encode()
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        self.respond(200,{'ready':True,'model':MODEL_ID}) if self.path=='/health' else self.respond(404,{'error':'Not found'})
    def do_POST(self):
        if self.path!='/generate':return self.respond(404,{'error':'Not found'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>128000: return self.respond(413,{'error':'Request size invalid'})
            data=json.loads(self.rfile.read(size))
            messages=data['messages']
            if not isinstance(messages,list) or not messages:raise ValueError('Messages required')
            prompt=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            if len(tokenizer.encode(prompt))>12000:return self.respond(413,{'error':'Context too long'})
            text=generate(model,tokenizer,prompt=prompt,max_tokens=min(int(data.get('max_tokens',1536)),1536),sampler=make_sampler(temp=0),verbose=False)
            self.respond(200,{'text':text,'model':MODEL_ID})
        except Exception as e:self.respond(500,{'error':type(e).__name__})


if __name__=='__main__':
    print('Model ready at http://127.0.0.1:8081',flush=True)
    HTTPServer(('127.0.0.1',8081),Handler).serve_forever()
