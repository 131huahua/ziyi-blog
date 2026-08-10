# 验证修复：div 平衡 + tab-ai 层级
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
html = open('templates/admin.html', encoding='utf-8').read()
print('模板 div 开:', html.count('<div'), '闭:', html.count('</div>'))

i_cloud = html.find('id="tab-cloud"')
i_ai = html.find('id="tab-ai"')
mid = html[i_cloud:i_ai]
print('cloud→ai div 开:', mid.count('<div'), '闭:', mid.count('</div>'))

# 用 HTMLParser 验证 tab-ai 的父级
from html.parser import HTMLParser
class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.ai_parent = None
        self.done = False
    def handle_starttag(self, tag, attrs):
        if self.done: return
        self.stack.append(tag)
        d = dict(attrs)
        if d.get('id') == 'tab-ai':
            # 找最近的 div 祖先
            self.ai_parent = self.stack[-2] if len(self.stack) > 1 else None
            self.done = True
    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

p = P()
p.feed(html)
print('tab-ai 的直接父标签:', p.ai_parent)
