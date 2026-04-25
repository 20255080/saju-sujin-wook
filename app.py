"""
사주 문답 v3 - Flask 백엔드 (배포용)

배포 변경점:
- 비밀번호 보호 추가 (SITE_PASSWORD 환경변수)
- 동적 포트 사용 (Render의 PORT 환경변수)
- 외부 접속 허용 (host='0.0.0.0')
"""

from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, Response
from anthropic import Anthropic
from lunar_python import Solar
from dotenv import load_dotenv
from data_loader import load_all_data
from functools import wraps
import os
import secrets

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
    },
    "신성욱": {
        "name": "신성욱", "gender": "남",
        "date": "1996-08-24", "time": "12:30", "cal": "양력",
        "birthplace": "창원 출생, 현재 울산 거주",
        "occupation": "회사원",
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
        "year_pillar": e.getYear(),
        "month_pillar": e.getMonth(),
        "day_pillar": e.getDay(),
        "time_pillar": e.getTime(),
        "day_master": e.getDayGan(),
    }


def get_saju_for_profile(name):
    p = PRESET_PROFILES[name]
    y, m, d = map(int, p["date"].split("-"))
    h, mi = map(int, p["time"].split(":"))
    return calculate_saju(y, m, d, h, mi, p["cal"] == "음력")


SAJU_CACHE = {name: get_saju_for_profile(name) for name in PRESET_PROFILES}


# ============================================================
# 비밀번호 보호 데코레이터
# ============================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if SITE_PASSWORD and not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


LOGIN_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>사주 문답 · 入</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500&family=Noto+Serif+KR:wght@200;300;400&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0d0b07; color: #f0e8d6; font-family: 'Noto Serif KR', serif; font-weight: 300; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background-image: radial-gradient(ellipse 80% 60% at 50% 50%, rgba(201,169,97,0.10) 0%, transparent 60%); }
  .box { width: 90%; max-width: 380px; padding: 50px 36px; background: #161210; border: 1px solid #2a241c; text-align: center; }
  .ornament { font-family: 'Cormorant Garamond', serif; color: #c9a961; font-size: 14px; letter-spacing: 1em; margin-bottom: 20px; padding-left: 1em; }
  h1 { font-weight: 200; font-size: 36px; letter-spacing: 0.15em; margin-bottom: 8px; }
  .accent { color: #c9a961; font-weight: 400; }
  .sub { color: #b8ad95; font-size: 11px; letter-spacing: 0.4em; font-family: 'Cormorant Garamond', serif; text-transform: uppercase; margin-bottom: 36px; }
  input[type=password] { width: 100%; background: transparent; border: none; border-bottom: 1px solid #3d3528; color: #f0e8d6; font-family: inherit; font-size: 16px; padding: 12px 4px; text-align: center; letter-spacing: 0.15em; transition: border-color 0.25s; }
  input[type=password]:focus { outline: none; border-bottom-color: #c9a961; }
  button { margin-top: 28px; background: transparent; border: 1px solid #c9a961; color: #c9a961; font-family: 'Noto Serif KR', serif; font-size: 13px; letter-spacing: 0.5em; padding: 14px 36px; cursor: pointer; transition: all 0.3s; }
  button:hover { background: #c9a961; color: #0d0b07; letter-spacing: 0.6em; padding: 14px 44px; }
  .err { color: #8b2635; font-size: 12px; margin-top: 16px; font-style: italic; }
</style>
</head>
<body>
<form class="box" method="post">
  <div class="ornament">四 柱 問 答</div>
  <h1>사주 <span class="accent">문답</span></h1>
  <div class="sub">Enter the gate</div>
  <input type="password" name="password" placeholder="비밀번호" autofocus>
  <button type="submit">入</button>
  __ERROR__
</form>
</body>
</html>"""


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


# ============================================================
# 메인 라우팅
# ============================================================
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
            **p,
            "saju": SAJU_CACHE[name],
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
사주팔자: {s['year_pillar']} {s['month_pillar']} {s['day_pillar']} {s['time_pillar']} (일간 {s['day_master']})"""
    
    if data:
        block += f"\n\n[{name} 사주 자료]\n{data}"
    
    return block


def build_system_prompt(mode):
    if mode == "compatibility":
        context = build_person_block("김수진") + "\n\n" + ("="*50) + "\n\n" + build_person_block("신성욱")
        scope = "두 사람의 관계·궁합·상호작용을 분석"
    else:
        context = build_person_block(mode)
        scope = f"{mode} 한 사람의 사주와 운을 분석"
    
    return f"""당신은 한국 명리학 해석가입니다. 아래에 제공된 사주 자료를 근거로 사용자의 질문에 답하세요.

{context}

[분석 범위]
{scope}

[답변 구조 — 반드시 이 4섹션 순서로]

[결론]
한 문장으로 핵심 답을 명료하게.

[사주 근거]
위 자료의 일주·십성·오행·대운·연운·살 중 어느 부분이 결론을 뒷받침하는지 2-3문장. 자료에서 직접 인용하되 길게 풀어쓰지 마세요.

[현실 조언]
구체적 행동·결정·습관 1-2개.

[최적 표현]
- 관계 질문이면: 상대에게 할 말의 실제 문장 예시 1-2개를 따옴표로.
- 개인 질문이면: 가져갈 마음가짐과 접근법.

[규칙]
- 자료에 있는 내용을 다시 길게 풀어쓰지 마세요. 질문에 답하는 데 필요한 핵심만 인용.
- 전체 분량 500-700자. 짧고 명료하게.
- 마크다운 헤더(#)나 **굵은 글씨**는 절대 쓰지 마세요. 섹션 라벨은 반드시 [대괄호]로.
- 결정론적 단정("반드시 헤어진다", "확실히 망한다") 금지. 가능성과 경향성으로 표현.
- 이모지 절대 금지."""


@app.route("/api/ask", methods=["POST"])
@login_required
def ask():
    try:
        data = request.json
        mode = data.get("mode", "compatibility")
        input_type = data.get("input_type", "simple")
        question = data.get("question", "").strip()
        history = data.get("history", [])
        
        if not question:
            return jsonify({"error": "질문이 비어있습니다."}), 400
        
        if mode != "compatibility" and mode not in PRESET_PROFILES:
            return jsonify({"error": f"알 수 없는 모드: {mode}"}), 400
        
        system_prompt = build_system_prompt(mode)
        
        if input_type == "situation":
            format_note = "이 질문은 [긴 상황 설명] 입니다. 답변에 ① 그 행동/사건의 사주적 의미, ② 발생 이유, ③ 대응 방향을 포함하세요."
        else:
            format_note = "이 질문은 [간단한 직접 질문] 입니다. 명료하게 답하세요."
        
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
            max_tokens=1200,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=[{"role": "user", "content": user_message}]
        )
        
        answer = "".join(b.text for b in response.content if b.type == "text").strip()
        
        usage = response.usage
        cache_read = getattr(usage, 'cache_read_input_tokens', 0)
        cache_write = getattr(usage, 'cache_creation_input_tokens', 0)
        regular_input = usage.input_tokens
        output = usage.output_tokens
        if cache_read > 0:
            print(f"  💰 캐시 적중! 읽기: {cache_read:,} / 일반: {regular_input:,} / 출력: {output:,}")
        elif cache_write > 0:
            print(f"  📝 캐시 생성: {cache_write:,} / 일반: {regular_input:,} / 출력: {output:,}")
        else:
            print(f"  입력: {regular_input:,} / 출력: {output:,}")
        
        return jsonify({"answer": answer, "mode": mode, "input_type": input_type})
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
