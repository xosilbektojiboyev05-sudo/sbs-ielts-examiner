import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename
from groq import Groq

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'assets/images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# API kalitni muhit o'zgaruvchisidan o'qish
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Testlar bazasi (xotirada saqlash uchun)
tests_db = []


# --- BOSHI SAHIFA ROUTI ---

@app.route('/')
def home():
    return render_template('index.html')


# --- ADMIN PANEL UCHUN YO'LLAR ---

@app.route('/api/add-test', methods=['POST'])
def add_test():
    try:
        skill = request.form.get('skill', '')
        title = request.form.get('title', '')
        content = request.form.get('content', '')
        
        image_url = ""
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                image_url = f"../assets/images/{filename}"

        new_test = {
            "id": len(tests_db) + 1,
            "skill": skill,
            "title": title,
            "content": content,
            "image": image_url
        }
        tests_db.append(new_test)
        
        return jsonify({
            "status": "success", 
            "message": "Test va rasm muvaffaqiyatli saqlandi! 🚀"
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route('/api/get-tests', methods=['GET'])
def get_tests():
    return jsonify(tests_db)


@app.route('/api/delete-test/<int:test_id>', methods=['DELETE'])
def delete_test(test_id):
    global tests_db
    tests_db = [t for t in tests_db if t["id"] != test_id]
    return jsonify({"status": "success", "message": "Test o'chirildi!"})


# --- AI BAHOLASH UCHUN YO'L ---

@app.route('/api/ai-evaluate', methods=['POST'])
def ai_evaluate():
    try:
        data = request.get_json(silent=True) or {}

        task1_text = str(data.get('task1') or '').strip()
        task2_text = str(data.get('task2') or '').strip()

        if not task1_text and not task2_text:
            return jsonify({
                "success": False,
                "error": "Iltimos, Task 1 yoki Task 2 essayini kiriting."
            }), 400

        if not os.environ.get("GROQ_API_KEY"):
            return jsonify({
                "success": False,
                "error": "GROQ_API_KEY sozlanmagan. API kalitini muhit o'zgaruvchisiga kiriting."
            }), 500

        full_prompt = f"""
Evaluate the following IELTS Academic Writing responses using
the official IELTS Writing assessment criteria.

IMPORTANT RULES:
- Evaluate only the essay or essays that are provided.
- Do not invent information about a chart, graph, map or question.
- For Task 1, assess Task Achievement.
- For Task 2, assess Task Response.
- Assess Coherence and Cohesion, Lexical Resource, and
  Grammatical Range and Accuracy separately.
- Give a score from 0 to 9 in half-band increments for each
  criterion: for example, 5.0, 5.5, 6.0, 6.5, 7.0.
- Base every score on evidence in the student's actual writing.
- Do not give a high score simply because the essay is long
  or contains advanced vocabulary.
- Identify inaccurate data, missing overview, weak comparisons,
  unsupported arguments, repetition, grammar errors and
  unnatural word choices when applicable.
- Do not invent mistakes that are not present.
- Explain feedback in Uzbek, but preserve English examples.
- Be honest and consistent. Do not inflate scores.
- Distinguish between an estimated AI score and an official
  IELTS result.

TASK 1 ESSAY:
{task1_text if task1_text else "NOT PROVIDED"}

TASK 2 ESSAY:
{task2_text if task2_text else "NOT PROVIDED"}

Use this exact report structure in Markdown:

# IELTS Writing Evaluation

## Task 1
If Task 1 was provided:
| Criterion | Band | Explanation |
| Task Achievement | score | explanation |
| Coherence & Cohesion | score | explanation |
| Lexical Resource | score | explanation |
| Grammatical Range & Accuracy | score | explanation |

Give the estimated Task 1 band and explain the main reasons.
If Task 1 was not provided, write "Task 1 essay taqdim etilmadi."

## Task 2
If Task 2 was provided:
| Criterion | Band | Explanation |
| Task Response | score | explanation |
| Coherence & Cohesion | score | explanation |
| Lexical Resource | score | explanation |
| Grammatical Range & Accuracy | score | explanation |

Give the estimated Task 2 band and explain the main reasons.
If Task 2 was not provided, write "Task 2 essay taqdim etilmadi."

## Overall Writing Band
If both tasks were provided, estimate the combined Writing score.
Task 2 carries twice the weight of Task 1.
Calculate the average using the two task-level bands:
(Task 1 band + 2 * Task 2 band) / 3.
Round the result to the nearest half band, following IELTS-style
rounding. Show the unrounded calculation and the estimated final
band.

If only one task was provided, do not pretend to calculate a
complete IELTS Writing score. Report only the estimated band for
the submitted task.

## Main Strengths
List the three most important strengths.

## Main Problems
List the three most important weaknesses, with examples from
the essay wherever possible.

## Corrections
Show selected original phrases and their improved versions.
Do not rewrite the entire essay unless necessary.

## How to Improve
Give three specific, practical steps for reaching the next band.

Remember: IELTS Writing criteria are assessed separately.
Task 1 and Task 2 have different Task Achievement/Task Response
criteria. Be specific, evidence-based and fair.
"""

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a rigorous IELTS Academic Writing assessor. "
                        "Apply IELTS public band descriptors carefully. "
                        "Assess the submitted text, not an imagined essay. "
                        "Give criterion-specific evidence and realistic "
                        "estimated scores. Never claim to be an official "
                        "IELTS examiner or to provide an official result."
                    )
                },
                {
                    "role": "user",
                    "content": full_prompt
                }
            ],
            model="openai/gpt-oss-20b",
            temperature=0.2,
            max_tokens=3500
        )

        ai_response = chat_completion.choices[0].message.content

        if not ai_response:
            return jsonify({
                "success": False,
                "error": "AI javobi bo'sh qaytdi. Qayta urinib ko'ring."
            }), 502

        return jsonify({
            "success": True,
            "feedback": ai_response
        })

    except Exception as e:
        app.logger.exception("IELTS evaluation error")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/ai-evaluate-speaking', methods=['POST'])
def ai_evaluate_speaking():
    try:
        data = request.get_json(silent=True) or {}

        part1 = str(data.get('part1') or '').strip()
        part2 = str(data.get('part2') or '').strip()
        part3 = str(data.get('part3') or '').strip()
        audio_transcript = str(data.get('transcript') or '').strip()

        if not any([part1, part2, part3, audio_transcript]):
            return jsonify({
                "success": False,
                "error": "Iltimos, Speaking Part 1, Part 2 yoki Part 3 javobini kiriting."
            }), 400

        if not os.environ.get("GROQ_API_KEY"):
            return jsonify({
                "success": False,
                "error": "GROQ_API_KEY sozlanmagan. API kalitini tekshiring."
            }), 500

        full_prompt = f"""
You are assessing an IELTS Speaking practice response.

Assess the available responses using the four official IELTS
Speaking assessment criteria:

1. Fluency and Coherence
2. Lexical Resource
3. Grammatical Range and Accuracy
4. Pronunciation

Candidate responses:

PART 1:
{part1 if part1 else "NOT PROVIDED"}

PART 2:
{part2 if part2 else "NOT PROVIDED"}

PART 3:
{part3 if part3 else "NOT PROVIDED"}

Additional speech transcript, if available:
{audio_transcript if audio_transcript else "NOT PROVIDED"}

STRICT ASSESSMENT RULES:
- Explain the evaluation in Uzbek. Keep English examples unchanged.
- Give criterion scores from 0 to 9 in half-band increments.
- Base scores on evidence in the provided responses.
- Do not invent mistakes or claim the candidate said something
  that is absent from the supplied text.
- Evaluate grammar, vocabulary, relevance, development of ideas,
  and coherence using the available answers.
- Evaluate Fluency and Coherence cautiously if only written
  transcripts are available.
- Do not claim to have heard pronunciation from text.
- If no audio is supplied, mark Pronunciation as
  "Audio kerak" rather than inventing a score.
- If audio is not available to this endpoint, explicitly state
  that pronunciation, individual sounds, stress, and intonation
  cannot be reliably assessed from text alone.
- If only one Speaking part is provided, assess that part only.
  Do not pretend that one short answer represents a complete
  IELTS Speaking test.
- Give a realistic estimated score. This is practice feedback,
  not an official IELTS result.

Return the report in this structure:

# IELTS Speaking Evaluation

## 1. Fluency and Coherence
Band: [score or limited evidence]
- Kuchli tomonlar
- Kamchiliklar
- Matndan dalillar

## 2. Lexical Resource
Band: [score]
- Lug'at boyligi va so'z birikmalari
- Takrorlangan yoki noto'g'ri ishlatilgan so'zlar
- Yaxshilangan inglizcha variantlar

## 3. Grammatical Range and Accuracy
Band: [score]
- Grammatik xatolar
- Original phrase -> Corrected phrase
- Murakkab gaplardan foydalanish bo'yicha tavsiya

## 4. Pronunciation
- Audio mavjud bo'lsa, faqat haqiqatan eshitilgan dalillarga
  asoslanib bahola.
- Audio mavjud bo'lmasa, band qo'yma va audio kerakligini ayt.

## 5. Estimated Speaking Band
- Audio mavjud bo'lsa va barcha mezonlarni baholashga
  yetarli dalil bo'lsa, to'rtta mezonni hisobga olib
  taxminiy umumiy band ber.
- Audio bo'lmasa, faqat matn asosidagi taxminiy tahlilni ber.
  To'liq Speaking bandini ishonchli aniqlab bo'lmasligini ayt.

## 6. Main Strengths
Uchta asosiy kuchli tomon.

## 7. Main Problems
Uchta asosiy kamchilik va matndan dalillar.

## 8. Improved Answer
Nomzodning asosiy ma'nosini saqlagan holda tabiiyroq
inglizcha javob namunasi. Faqat taqdim etilgan savol va
javob ma'lumotlari bunga yetarli bo'lsa yoz.

## 9. How to Improve
Keyingi bandga chiqish uchun uchta aniq tavsiya.
"""

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a rigorous IELTS Speaking practice assessor. "
                        "Apply the four public IELTS Speaking criteria fairly. "
                        "Never invent audio evidence or pronunciation errors. "
                        "Distinguish text-based feedback from audio-based "
                        "assessment. Never claim to provide an official score."
                    )
                },
                {
                    "role": "user",
                    "content": full_prompt
                }
            ],
            model="openai/gpt-oss-20b",
            temperature=0.2,
            max_tokens=3500
        )

        ai_response = chat_completion.choices[0].message.content

        if not ai_response:
            return jsonify({
                "success": False,
                "error": "AI javobi bo'sh qaytdi. Qayta urinib ko'ring."
            }), 502

        return jsonify({
            "success": True,
            "feedback": ai_response
        })

    except Exception as e:
        app.logger.exception("IELTS Speaking evaluation error")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)