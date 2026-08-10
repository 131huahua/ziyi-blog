# 检查 tab-cloud 与 tab-ai 的嵌套关系
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
html = open('templates/admin.html', encoding='utf-8').read()

i_cloud = html.find('id="tab-cloud"')
i_ai = html.find('id="tab-ai"')
print('tab-cloud at:', i_cloud)
print('tab-ai at:', i_ai)

# tab-ai 前 500 字符（看它前面是什么结构）
print('--- tab-ai 前 600 字符 ---')
print(html[i_ai-600:i_ai])
print()
print('--- tab-ai 前 100 字符 ---')
print(repr(html[i_ai-100:i_ai]))
