"""Opt-in live model probe with fictional input and a six-call total hard cap.

Never imports web_app, connects to an account database, or reads real interviews.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keys', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    from run_cloud import read_model_keys
    from openai import OpenAI
    from indexed_memo import IndexedMemoPipeline
    from analysis_contracts import check_memo_source
    keys = read_model_keys(args.keys)
    client = OpenAI(api_key=keys['DEEPSEEK_API_KEY'], base_url='https://api.deepseek.com',
                    timeout=90, max_retries=0)
    count, tokens = 0, 0
    def create(request):
        nonlocal count, tokens
        if count >= 6:
            raise RuntimeError('Synthetic probe six-call cap reached')
        count += 1
        reply = client.chat.completions.create(**request)
        tokens += getattr(reply.usage, 'total_tokens', 0) or 0
        return reply
    cases = [
        ('negation', '访谈者：费用会让您拒绝服务吗？\n受访者：我是虚构受访者小林。我现在仍坐地铁上班。我担心费用，但没有拒绝服务，只有报销不足时才会犹豫。'),
        ('no-answer', '访谈者：您对社区服务有什么看法？\n受访者：这个问题我没想好，今天暂时不谈。'),
    ]
    with tempfile.TemporaryDirectory(prefix='workbench-memo-index-probe-') as root:
        for name, text in cases:
            started, before = time.monotonic(), count
            pipe = IndexedMemoPipeline(text, Path(root)/name, None, create)
            memo = pipe.generate()
            check_memo_source(memo, text)
            pipe.run.complete()
            print(json.dumps(dict(case=name, calls=count-before, seconds=round(time.monotonic()-started, 2),
                                  exact_evidence=True, summary=memo['summary'],
                                  views=[dict(title=v['title'],summary=v['summary']) for v in memo['viewpoints']],
                                  evidence_count=len(memo['evidence'])), ensure_ascii=False), flush=True)
    print(json.dumps(dict(total_calls=count, total_tokens=tokens, real_interviews_used=False,
                          production_accounts_modified=False)), flush=True)


if __name__ == '__main__':
    main()
