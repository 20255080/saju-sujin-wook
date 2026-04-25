"""
사주 문답 v3 - Flask 백엔드

v3 변경점:
- 답변 4섹션 고정: 결론 → 사주 근거 → 현실 조언 → 최적 표현
- 입력 모드 분리: 간단한 질문 / 긴 상황 설명
- 프롬프트 캐싱(prompt caching) 도입 → 같은 모드 후속 질문에서 토큰 90% 절약
- 시스템 프롬프트 간결화
"""

from flask import Flask, request, jsonify, send_from_directory
from anthropic import Anthropic
from lunar_python import Solar
from dotenv import load_dotenv
from data_loader import load_all_data
import os

load_dotenv()
app = Flask(__name__)
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PERSON_DATA = load_all_data()

# 두 분 자동 내장 정보
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


def build_person_block(name):
    """한 사람의 정보+사주+자료를 한 블록으로 합치기"""
    p = PRESET_PROFILES[name]
    s = SAJU_CACHE[name]
    data = PERSON_DATA.get(name, "")
    
    block = f"""[{name}]
{p['gender']}, {p['date']} {p['time']} {p['cal']} | {p['occupation']} | {p['birthplace']}
사주팔자: {s['year_pillar']} {s['month_pillar']} {s['day_pillar']} {s['time_pillar']} (일간 {s['day_master']})"""
    
    if data:
        block += f"\n\n[{name} 사주 자료]\n{data}"
    
    return block


# 모드별 시스템 프롬프트 미리 만들어두기 (캐시 hit률 최대화)
def build_system_prompt(mode):
    """모드별로 캐시 가능한 시스템 프롬프트 구성"""
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


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/profiles")
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


@app.route("/api/ask", methods=["POST"])
def ask():
    try:
        data = request.json
        mode = data.get("mode", "compatibility")
        input_type = data.get("input_type", "simple")  # simple / situation
        question = data.get("question", "").strip()
        history = data.get("history", [])
        
        if not question:
            return jsonify({"error": "질문이 비어있습니다."}), 400
        
        if mode != "compatibility" and mode not in PRESET_PROFILES:
            return jsonify({"error": f"알 수 없는 모드: {mode}"}), 400
        
        # 시스템 프롬프트 (캐시 가능 — 자료가 매 요청마다 똑같음)
        system_prompt = build_system_prompt(mode)
        
        # 동적 부분 (매 요청마다 달라짐)
        if input_type == "situation":
            format_note = "이 질문은 [긴 상황 설명] 입니다. 답변에 ① 그 행동/사건의 사주적 의미, ② 발생 이유, ③ 대응 방향을 포함하세요."
        else:
            format_note = "이 질문은 [간단한 직접 질문] 입니다. 명료하게 답하세요."
        
        history_text = ""
        if history:
            recent = history[-1]  # 최근 1개만 (토큰 절약)
            history_text = f"\n[직전 대화]\n질문: {recent['q']}\n답변 요약: {recent['a'][:150]}...\n"
        
        user_message = f"""{format_note}
{history_text}
[질문]
{question}"""
        
        # API 호출 (prompt caching 적용)
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1200,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}  # 5분 캐시
                }
            ],
            messages=[{"role": "user", "content": user_message}]
        )
        
        answer = "".join(b.text for b in response.content if b.type == "text").strip()
        
        # 캐시 사용량 정보 (디버깅용 콘솔 출력)
        usage = response.usage
        cache_read = getattr(usage, 'cache_read_input_tokens', 0)
        cache_write = getattr(usage, 'cache_creation_input_tokens', 0)
        regular_input = usage.input_tokens
        output = usage.output_tokens
        if cache_read > 0:
            print(f"  💰 캐시 적중! 캐시 읽기: {cache_read:,} 토큰 (정가의 10%) / 일반 입력: {regular_input:,} / 출력: {output:,}")
        elif cache_write > 0:
            print(f"  📝 캐시 생성: {cache_write:,} 토큰 (정가의 125%) / 일반 입력: {regular_input:,} / 출력: {output:,}")
        else:
            print(f"  입력: {regular_input:,} 토큰 / 출력: {output:,} 토큰")
        
        return jsonify({
            "answer": answer,
            "mode": mode,
            "input_type": input_type,
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  사주 문답 v3 서버 시작")
    print("  http://localhost:5000")
    print("  종료: Ctrl+C")
    print("="*60 + "\n")
    app.run(debug=True, port=5000)
