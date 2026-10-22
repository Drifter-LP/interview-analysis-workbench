"""Bounded streaming JSON reads: preserve responses, stop obvious degeneration."""
import json
import re


def check_generation(content, allow_array=False):
    stripped = content.lstrip()
    if stripped and stripped[0] not in ('{[' if allow_array else '{'):
        raise ValueError('模型输出不是JSON对象，已提前中止异常生成')
    if len(content) > 256 and not stripped:
        raise ValueError('模型持续输出空白，已提前中止')
    # Summaries should not contain long runs of the same short phrase/token.
    tail = content[-2048:]
    match = re.search(r'(.{1,32}?)\1{11,}', tail, flags=re.S)
    if match and len(match.group(0)) >= 160:
        raise ValueError('模型出现长段重复生成，已提前中止')


def request_json(client, *, model, prompt, payload, budget, guarded=False, on_response=None,
                 array_key=None, on_normalization=None):
    kwargs = dict(model=model, temperature=0, max_tokens=budget,
                  response_format={'type': 'json_object'}, extra_body={'enable_thinking': False},
                  messages=[{'role': 'system', 'content': prompt},
                            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}])
    if not guarded:
        response = client.chat.completions.create(**kwargs)
        artifact = response.model_dump(mode='json')
        if on_response:
            on_response(artifact)
        if response.choices[0].finish_reason != 'stop':
            error = ValueError if response.choices[0].finish_reason == 'length' else RuntimeError
            raise error('模型输出未完整结束：' + str(response.choices[0].finish_reason))
        result = json.loads(response.choices[0].message.content or '')
    else:
        stream = None
        artifact = {'model': model, 'streaming': True, 'chunks': [], 'usage': None,
                    'choices': [{'finish_reason': None, 'message': {'content': ''}}]}
        try:
            stream = client.chat.completions.create(**kwargs, stream=True, stream_options={'include_usage': True})
            for chunk in stream:
                artifact['chunks'].append(chunk.model_dump(mode='json'))
                artifact['model'] = getattr(chunk, 'model', None) or artifact['model']
                if getattr(chunk, 'usage', None):
                    artifact['usage'] = chunk.usage.model_dump(mode='json')
                for choice in chunk.choices:
                    artifact['choices'][0]['message']['content'] += choice.delta.content or ''
                    if choice.finish_reason is not None:
                        artifact['choices'][0]['finish_reason'] = choice.finish_reason
                check_generation(artifact['choices'][0]['message']['content'], allow_array=bool(array_key))
            if artifact['choices'][0]['finish_reason'] != 'stop':
                error = ValueError if artifact['choices'][0]['finish_reason'] == 'length' else RuntimeError
                raise error('模型输出未完整结束：' + str(artifact['choices'][0]['finish_reason']))
            result = json.loads(artifact['choices'][0]['message']['content'])
        except ValueError as exc:
            artifact['local_error'] = str(exc)
            artifact['locally_aborted'] = artifact['choices'][0]['finish_reason'] is None
            raise
        finally:
            if stream is not None and hasattr(stream, 'close'):
                stream.close()
            if on_response:
                on_response(artifact)
    if isinstance(result, list) and array_key:
        result = {array_key: result}
        if on_normalization:
            on_normalization({'operation': 'bare_array_wrapped', 'key': array_key})
    if not isinstance(result, dict):
        raise ValueError('模型未返回JSON对象')
    return result
