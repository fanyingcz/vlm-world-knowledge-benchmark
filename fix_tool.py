import json
import re

def fix_json_file(input_file, output_file=None):
    """
    1. 检测所有简答题的 is_correct 是否与 short_answer_evaluation 的判定一致，并修正。
    2. 遍历所有题目（包括选择题、判断题、简答题），重新统计正确的总数。
    3. 更新 summary 部分，确保统计数据与实际一致。
    """
    if output_file is None:
        output_file = input_file

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # ---------- 第一步：修正简答题的 is_correct ----------
    fixed_count = 0
    for item in data['detailed_results']:
        if item.get('type') != '简答题':
            continue

        eval_text = item.get('short_answer_evaluation', '')
        # 提取最后的判定结论
        match = re.search(r'\*\*判定：\*\*\s*(正确|错误)', eval_text)
        if not match:
            print(f"警告：无法提取判定文本 (subject {item.get('subject_index')})")
            continue

        judgement = match.group(1)
        expected = (judgement == '正确')
        actual = item.get('is_correct')

        if actual != expected:
            item['is_correct'] = expected
            fixed_count += 1
            print(f"修正 subject {item['subject_index']} Q{item['question_index_in_subject']}: {actual} -> {expected}")

    # ---------- 第二步：重新统计全部题目的正确情况 ----------
    total_questions = len(data['detailed_results'])
    correct_count = sum(1 for item in data['detailed_results'] if item.get('is_correct') is True)
    incorrect_count = total_questions - correct_count
    accuracy_percent = round(correct_count / total_questions * 100, 2) if total_questions > 0 else 0.0

    # ---------- 第三步：更新 summary ----------
    data['summary']['total_questions'] = total_questions
    data['summary']['correct_count'] = correct_count
    data['summary']['incorrect_count'] = incorrect_count
    data['summary']['accuracy_percent'] = accuracy_percent

    # ---------- 第四步：写回文件 ----------
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n修正了 {fixed_count} 条简答题的 is_correct。")
    print(f"更新 summary: 总题数 {total_questions}, 正确 {correct_count}, 错误 {incorrect_count}, 正确率 {accuracy_percent}%")
    print(f"结果已保存至 {output_file}")

if __name__ == '__main__':
    fix_json_file('evaluation_results_通义千问_(Qwen)_mode2.json', 'evaluation_results_通义千问_(Qwen)_mode2_fixed.json')