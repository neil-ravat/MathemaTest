from pathlib import Path
import hashlib,json,os,re,shutil,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
from openai import OpenAI
from scripts.run_gpt4o_smoke import GroqCompletion,write_json
from src.verification.curriculum_audit import GroundedChallenge,validate_review
HERE=Path(__file__).resolve().parent

if (HERE/'manifest.json').exists():raise ValueError('Do not overwrite a live run')
request=json.loads((HERE/'request.json').read_text())
source=ROOT/'src/verification/curriculum_audit.py'
shutil.copyfile(source,HERE/'curriculum_audit_snapshot.py')
write_json(HERE/'manifest.json',dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    request_sha256=hashlib.sha256((HERE/'request.json').read_bytes()).hexdigest(),
    scope='One final-review replay; same evidence/schema/output cap, compact source index. Previous stage outputs reused.'))
load_dotenv(ROOT/'.env',override=False)
client=OpenAI(api_key=os.environ['GROQ_API_KEY'],base_url='https://api.groq.com/openai/v1',max_retries=0,timeout=90)
def create(**kwargs):
    try:return client.chat.completions.create(**kwargs)
    except Exception as exc:
        # Keep numeric capacity details only, not the provider's organization ID.
        write_json(HERE/'capacity_error.json',dict(http_status=getattr(exc,'status_code',None),
            counts=re.findall(r'(Limit|Requested)\s+(\d+)',str(exc),re.I)))
        raise
live=GroqCompletion(create,HERE/'usage.json',max_requests=2)
request['max_tokens']=request.pop('max_completion_tokens')
result={}
try:
    response=live(**request);write_json(HERE/'response.json',response.model_dump())
    if response.choices[0].finish_reason!='stop':raise ValueError('Incomplete output')
    review=GroundedChallenge.model_validate_json(response.choices[0].message.content)
    validate_review(review,json.loads(request['messages'][1]['content']))
    result=dict(status='VALID_REVIEW',review=review.model_dump())
except Exception as exc:result=dict(status='ERROR',error_type=type(exc).__name__,error=str(exc))
write_json(HERE/'result.json',result)
print(result['status'],flush=True)
