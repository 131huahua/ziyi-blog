# 检查 tab-cloud 完整结构（开头 + 结尾层级）
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
html = open('templates/admin.html', encoding='utf-8').read()

i_cloud = html.find('id="tab-cloud"')
i_ai = html.find('id="tab-ai"')

# tab-cloud 开头 800 字符
seg = html[i_cloud-50:i_cloud+900]
print('--- tab-cloud 开头 ---')
print(seg)

# tab-cloud 内部到 tab-ai 之间的 div 平衡
mid = html[i_cloud:i_ai]
print()
print('--- cloud 到 ai 之间: div开 =', mid.count('<div'), 'div闭 =', mid.count('</div>'))
