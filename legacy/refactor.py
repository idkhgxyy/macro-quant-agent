import os
import re

def refactor_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 如果文件没有用到 print，直接跳过
    if 'print(' not in content:
        return

    # 添加 logger 导入
    if 'from utils.logger import setup_logger' not in content:
        # 在第一个 import 或者 from 之后插入
        match = re.search(r'^(import|from) ', content, flags=re.MULTILINE)
        if match:
            idx = match.start()
            import_str = "from utils.logger import setup_logger\nlogger = setup_logger(__name__)\n\n"
            content = content[:idx] + import_str + content[idx:]
        else:
            # 如果没有 import，放在最上面
            import_str = "from utils.logger import setup_logger\nlogger = setup_logger(__name__)\n\n"
            content = import_str + content

    # 替换 print 为 logger.info，注意处理错误级别的 print 为 logger.warning / logger.error
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'^\s*print\(', line):
            if '❌' in line or '⚠️' in line or '🛑' in line or '失败' in line or '错误' in line or '警告' in line:
                lines[i] = re.sub(r'print\(', 'logger.warning(', line, count=1)
            else:
                lines[i] = re.sub(r'print\(', 'logger.info(', line, count=1)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

if __name__ == "__main__":
    files_to_refactor = [
        "core/agent.py",
        "data/retriever.py",
        "data/cache.py",
        "llm/volcengine.py",
        "backtest/engine.py",
        "execution/broker.py",
        "execution/portfolio.py",
        "run_llm_backtest.py",
        "run_agent.py"
    ]
    
    for file in files_to_refactor:
        filepath = os.path.join(os.path.dirname(__file__), file)
        if os.path.exists(filepath):
            refactor_file(filepath)
            print(f"Refactored {file}")
