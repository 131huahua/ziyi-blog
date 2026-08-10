# 批量转换：桌面 50 个香肠配方 docx → 博客 recipes/ 目录 Markdown
import sys, io, re
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document

SRC = Path(r'C:\Users\zzy\Desktop\50香肠配方')
DST = Path(__file__).parent / 'recipes' / '香肠'
DST.mkdir(parents=True, exist_ok=True)

def split_ingredients(text: str) -> list[str]:
    """按逗号/顿号/分号拆分原料"""
    items = re.split(r'[，,、；;]', text)
    return [i.strip() for i in items if i.strip()]

converted = 0
failed = []
for docx in sorted(SRC.glob('*.docx')):
    try:
        doc = Document(str(docx))
        paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        if not paras:
            failed.append(f'{docx.name}: 空文档')
            continue

        title = paras[0].rstrip('：:')
        # 去掉常见的"原料配方："尾缀，让标题更干净
        title = re.sub(r'(原料配方|配方|的做法)$', '', title).strip()

        # 分类段落：找原料段（含千克/克/斤等单位的段落）与步骤段
        ingr_lines, method_lines = [], []
        in_method = False
        for p in paras[1:]:
            if re.search(r'制作方法|加工方法|做法|工艺流程', p) and len(p) < 15:
                in_method = True
                continue
            if not in_method:
                ingr_lines.append(p)
            else:
                method_lines.append(p)

        # 拼原料（可能多段，合并拆分）
        ingr_text = '，'.join(ingr_lines)
        ingredients = split_ingredients(ingr_text) or ingr_lines

        md = [f'# {title}', '', '- 分类：香肠', '- 类型：配方', '', '## 原料', '']
        for i in ingredients:
            md.append(f'- {i}')
        md += ['', '## 制作方法', '']
        for m in method_lines:
            # 步骤编号规范化：1、 → 1.
            m2 = re.sub(r'^(\d+)[、.]\s*', r'\1. ', m)
            md.append(m2)
        md.append('')

        (DST / f'{docx.stem}.md').write_text('\n'.join(md), encoding='utf-8')
        converted += 1
    except Exception as e:
        failed.append(f'{docx.name}: {e}')

print(f'转换成功: {converted} 个')
if failed:
    print('失败:')
    for f in failed:
        print(' -', f)
