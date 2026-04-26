"""
사주 문답 v4 - Flask 백엔드

v4 변경점:
- lens 옵션 추가: both(기본) / saju(명리학만) / astro(점성술만)
- 결론 분량 확대 (1줄 → 2-3문장)
- 한자/전문용어 강력 금지, 쉬운 한국어 강제
- '최적 표현' 섹션은 옵션 (include_expression 플래그)
- 현실 조언은 1-2줄로 간결하게
"""

from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, Response
from anthropic import Anthropic
from lunar_python import Solar
from dotenv import load_dotenv
from data_loader import load_all_data
from functools import wraps
import os, secrets

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SITE_PASSWORD = os.getenv("SITE_PASSWORD", "")
PERSON_DATA = load_all_data()

PRESET_PROFILES = {
    "김수진": {
        "name": "김수진", "gender": "여",
        "date": "1996-05-22", "time": "12:30", "cal": "양력",
        "birthplace": "대구 출생, 현재 울산 거주",
        "occupation": "박사과정 대학원생",
        "mbti": "ISTJ → ISTP",
    },
    "신성욱": {
        "name": "신성욱", "gender": "남",
        "date": "1996-08-24", "time": "12:30", "cal": "양력",
        "birthplace": "창원 출생, 현재 울산 거주",
        "occupation": "회사원",
        "mbti": "ISTP → ISTJ-T",
    },
}


def calculate_saju(year, month, day, hour, minute, is_lunar=False):
    if is_lunar:
        from lunar_python import Lunar
        lunar = Lunar.fromYmdHms(year, month, day, hour, minute, 0)
    else:
        solar = Solar.fromYmdHms(year, month, day, hour, minute, 0)
        lunar = solar.getLunar()
    e = lunar.getEightChar()
    return {
        "year_pillar": e.getYear(), "month_pillar": e.getMonth(),
        "day_pillar": e.getDay(), "time_pillar": e.getTime(),
        "day_master": e.getDayGan(),
    }


def get_saju_for_profile(name):
    p = PRESET_PROFILES[name]
    y, m, d = map(int, p["date"].split("-"))
    h, mi = map(int, p["time"].split(":"))
    return calculate_saju(y, m, d, h, mi, p["cal"] == "음력")


SAJU_CACHE = {name: get_saju_for_profile(name) for name in PRESET_PROFILES}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if SITE_PASSWORD and not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


LOGIN_HTML = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>사주 문답 · 入</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500&family=Noto+Serif+KR:wght@200;300;400&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#0d0b07;color:#f0e8d6;font-family:'Noto Serif KR',serif;font-weight:300;min-height:100vh;display:flex;align-items:center;justify-content:center;background-image:radial-gradient(ellipse 80% 60% at 50% 50%,rgba(201,169,97,0.10) 0%,transparent 60%)}
  .box{width:90%;max-width:380px;padding:50px 36px;background:#161210;border:1px solid #2a241c;text-align:center}
  .ornament{font-family:'Cormorant Garamond',serif;color:#c9a961;font-size:14px;letter-spacing:1em;margin-bottom:20px;padding-left:1em}
  h1{font-weight:200;font-size:36px;letter-spacing:0.15em;margin-bottom:8px}
  .accent{color:#c9a961;font-weight:400}
  .sub{color:#b8ad95;font-size:11px;letter-spacing:0.4em;font-family:'Cormorant Garamond',serif;text-transform:uppercase;margin-bottom:36px}
  input[type=password]{width:100%;background:transparent;border:none;border-bottom:1px solid #3d3528;color:#f0e8d6;font-family:inherit;font-size:16px;padding:12px 4px;text-align:center;letter-spacing:0.15em;transition:border-color 0.25s}
  input[type=password]:focus{outline:none;border-bottom-color:#c9a961}
  button{margin-top:28px;background:transparent;border:1px solid #c9a961;color:#c9a961;font-family:'Noto Serif KR',serif;font-size:13px;letter-spacing:0.5em;padding:14px 36px;cursor:pointer;transition:all 0.3s}
  button:hover{background:#c9a961;color:#0d0b07;letter-spacing:0.6em;padding:14px 44px}
  .err{color:#8b2635;font-size:12px;margin-top:16px;font-style:italic}
</style></head><body>
<form class="box" method="post">
  <div class="ornament">四 柱 問 答</div>
  <h1>사주 <span class="accent">문답</span></h1>
  <div class="sub">Enter the gate</div>
  <input type="password" name="password" placeholder="비밀번호" autofocus>
  <button type="submit">入</button>
  __ERROR__
</form></body></html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    error_html = ""
    if request.method == "POST":
        if request.form.get("password") == SITE_PASSWORD:
            session["authenticated"] = True
            session.permanent = True
            return redirect(url_for("index"))
        error_html = '<div class="err">비밀번호가 맞지 않습니다.</div>'
    return Response(LOGIN_HTML.replace("__ERROR__", error_html), mimetype="text/html")


@app.route("/logout")
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/profiles")
@login_required
def profiles():
    result = {}
    for name, p in PRESET_PROFILES.items():
        result[name] = {
            **p, "saju": SAJU_CACHE[name],
            "has_data": bool(PERSON_DATA.get(name, "").strip()),
            "data_chars": len(PERSON_DATA.get(name, "")),
        }
    return jsonify(result)


def build_person_block(name):
    p = PRESET_PROFILES[name]
    s = SAJU_CACHE[name]
    data = PERSON_DATA.get(name, "")
    block = f"""[{name}]
{p['gender']}, {p['date']} {p['time']} {p['cal']} | {p['occupation']} | {p['birthplace']}
사주팔자: {s['year_pillar']} {s['month_pillar']} {s['day_pillar']} {s['time_pillar']} (일간 {s['day_master']})
MBTI 변화: {p.get('mbti', '미입력')}"""
    if data:
        block += f"\n\n[{name} 사주·점성술 통합 자료]\n{data}"
    return block


def build_system_prompt(mode, lens):
    """모드 + 렌즈별 시스템 프롬프트"""
    if mode == "compatibility":
        context = build_person_block("김수진") + "\n\n" + ("="*50) + "\n\n" + build_person_block("신성욱")
        scope = "두 사람의 관계·궁합·상호작용을 분석"
    else:
        context = build_person_block(mode)
        scope = f"{mode} 한 사람의 사주와 운"
    
    # 렌즈별 가이드
    if lens == "saju":
        lens_guide = """[사용할 시각: 명리학(사주)만]
이 답변은 한국 전통 명리학 관점으로만 분석합니다. 점성술 정보는 사용하지 마세요. 사주팔자, 일주, 십성, 오행, 대운/연운, 살과 귀인 등을 근거로 답하세요."""
    elif lens == "astro":
        lens_guide = """[사용할 시각: 점성술(서양 천문)만]
이 답변은 서양 점성술 관점으로만 분석합니다. 사주 정보는 사용하지 마세요. 행성 위치, 별자리, 12하우스, 행성 간 각도(어스펙트) 등을 근거로 답하세요."""
    else:  # both
        lens_guide = """[사용할 시각: 명리학 + 점성술 통합]
명리학(사주)과 서양 점성술 두 시각을 자연스럽게 함께 사용하세요. 두 시스템이 같은 사람을 다른 언어로 설명한다고 보고, 같은 결론을 가리킬 때는 그것을 보여주고, 다른 각도를 비추면 그것도 설명하세요."""
    
    return f"""당신은 한국 명리학(사주)과 서양 점성술 둘 다에 깊이 정통한 해석가입니다.

자료에는 두 종류가 다 들어있습니다:
- 명리학 자료: 사주팔자, 천간지지, 십성, 오행, 대운/연운, 살과 귀인 등
- 점성술 자료: 행성 위치, 별자리, 12하우스, 행성 간 각도(어스펙트) 등

{context}

[분석 범위]
{scope}

{lens_guide}

[★ 가장 중요한 작성 규칙 ★]

당신이 답변하는 사람은 명리학·점성술을 거의 모릅니다. 한자나 전문용어를 그대로 쓰면 못 알아봅니다. 다음 규칙을 절대 지키세요.

1. **한자·전문용어 직접 사용 금지**
   - 절대 쓰지 말 것: 己土, 癸水, 丙火, 比劫, 食傷, 印星, 官星, 財星, 일간, 일주, 월주, 시주, 천간, 지지, 합충형해, 도화, 역마, 화개, 재성, 인성, 관성, 비견, 겁재 등
   - 용어가 꼭 필요하면 풀이만 쓰세요. 한자나 한글 한자음(예: "기토", "계수") 모두 금지.

2. **풀이 말로 바꾸기 — 예시**
   - "己土 일간이라" → "흙처럼 차분하고 품어주는 성향이라"
   - "癸水라 섬세함" → "물처럼 섬세하고 깊이 있는 성향"
   - "丙火가 강해서" → "타고난 열정과 추진력이 강해서"
   - "比劫이 많아" → "자기 기준이 강하고 독립심이 큰 성향이라"
   - "재성이 강함" → "돈·성과·관계에 대한 욕구가 큰 편"
   - "인성이 약함" → "혼자 생각을 정리하는 시간이 부족할 수 있음"
   - "도화가 작용" → "사람을 끌어당기는 매력이 있는 시기"
   - "대운 전환기" → "인생의 큰 흐름이 바뀌는 시기"

3. **점성술 용어도 동일**
   - "9하우스 태양" → "깊이 있는 배움과 의미를 추구하는 마음 자리"
   - "토성과 60도 각" → "책임감과 부드럽게 연결돼 자연스러운 흐름"
   - "처녀자리 태양" → "분석적이고 꼼꼼한 기본 성향"

4. 어쩔 수 없이 전문 단어를 한 번 써야 한다면, 반드시 그 자리에서 풀이를 함께 적으세요. 예: "본인의 일간(=본인을 상징하는 글자)은 흙의 기운이라..."

[답변 구조 — 반드시 이 순서로]

[결론]
2-3문장으로 충분히. 단순히 "맞아요/안 맞아요"가 아니라 핵심 답 + 한 줄 부연 설명까지. 따뜻하고 단단한 톤. 예: "두 분은 깊이 있는 인연이지만, 표현 방식의 차이를 풀어가는 것이 핵심이에요. 한 분은 마음이 있어도 곧장 말하지 못하는 편이고, 다른 분은 확실한 표현이 안정감으로 느껴지는 분이거든요. 이 차이를 갈등으로 두지 말고 대화 주제로 만드는 것이 두 분의 과제예요."

[근거]
3-5문장. 위에 정한 시각(명리학만/점성술만/둘다)에 맞춰 분석. 반드시 쉬운 한국어로 풀어 설명. 한자/전문용어 직접 사용 절대 금지. 자료에서 어느 부분이 결론을 뒷받침하는지 자연스럽게 설명.

[현실 조언]
1-2가지 행동 제안만. 각각 한 문장 정도로 짧게. 길게 풀어쓰지 말고 핵심만.

__EXPRESSION_SECTION__

[추가 규칙]
- 분량: 결론 + 근거 + 조언 합쳐서 약 500-600자.
- 친근한 구어체("~예요", "~어요").
- 마크다운 헤더(#)나 **굵은 글씨** 절대 금지. 섹션 라벨은 [대괄호]만.
- 결정론적 단정("반드시 이렇게 된다") 금지. 가능성·경향으로.
- 이모지 절대 금지."""


@app.route("/api/ask", methods=["POST"])
@login_required
def ask():
    try:
        data = request.json
        mode = data.get("mode", "compatibility")
        input_type = data.get("input_type", "simple")
        lens = data.get("lens", "both")  # both / saju / astro
        include_expression = data.get("include_expression", False)
        question = data.get("question", "").strip()
        history = data.get("history", [])
        
        if not question:
            return jsonify({"error": "질문이 비어있습니다."}), 400
        if mode != "compatibility" and mode not in PRESET_PROFILES:
            return jsonify({"error": f"알 수 없는 모드: {mode}"}), 400
        if lens not in ["both", "saju", "astro"]:
            lens = "both"
        
        # 시스템 프롬프트
        system_prompt = build_system_prompt(mode, lens)
        
        # 최적 표현 섹션 포함 여부 처리
        if include_expression:
            expression_section = """[최적 표현]
관계 질문이면: 상대에게 할 말의 실제 문장 예시 1-2개를 따옴표로 ("나 지금 좀..."). 
개인 질문이면: 가져갈 마음가짐을 한 문장으로."""
        else:
            expression_section = "(최적 표현 섹션은 이번 답변에서 생략)"
        
        system_prompt = system_prompt.replace("__EXPRESSION_SECTION__", expression_section)
        
        # 동적 부분
        if input_type == "situation":
            format_note = "[긴 상황 설명] 입니다. ① 그 행동/사건의 의미, ② 발생 이유, ③ 대응 방향을 답변에 자연스럽게 녹이세요."
        else:
            format_note = "[간단한 직접 질문] 입니다. 명료하게 답하세요."
        
        history_text = ""
        if history:
            recent = history[-1]
            history_text = f"\n[직전 대화]\n질문: {recent['q']}\n답변 요약: {recent['a'][:150]}...\n"
        
        user_message = f"""{format_note}
{history_text}
[질문]
{question}"""
        
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            system=[
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
            ],
            messages=[{"role": "user", "content": user_message}]
        )
        
        answer = "".join(b.text for b in response.content if b.type == "text").strip()
        
        # 캐시 정보
        usage = response.usage
        cache_read = getattr(usage, 'cache_read_input_tokens', 0)
        cache_write = getattr(usage, 'cache_creation_input_tokens', 0)
        if cache_read > 0:
            print(f"  💰 캐시 적중! 읽기: {cache_read:,} / 일반: {usage.input_tokens:,} / 출력: {usage.output_tokens:,}")
        elif cache_write > 0:
            print(f"  📝 캐시 생성: {cache_write:,} / 일반: {usage.input_tokens:,} / 출력: {usage.output_tokens:,}")
        else:
            print(f"  입력: {usage.input_tokens:,} / 출력: {usage.output_tokens:,}")
        
        return jsonify({
            "answer": answer, "mode": mode,
            "input_type": input_type, "lens": lens,
            "include_expression": include_expression,
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
