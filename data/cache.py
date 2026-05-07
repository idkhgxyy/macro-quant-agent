from utils.logger import setup_logger
logger = setup_logger(__name__)

import json
import os
from datetime import datetime
import time

class CacheDB:
    """本地数据缓存，防止 API 被限流 (Rate Limit)"""
    def __init__(self, filepath="data_cache.json"):
        self.filepath = filepath
        self.cache = {}
        self.load_cache()
        
    def load_cache(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    self.cache = json.load(f)
            except:
                pass
                
    def get(self, key):
        if key not in self.cache:
            return None

        record = self.cache.get(key, {})
        expires_at = record.get("expires_at")
        if isinstance(expires_at, (int, float)):
            if time.time() <= float(expires_at):
                return record.get("data")
            return None

        today = datetime.now().strftime("%Y-%m-%d")
        if record.get("date") == today:
            return record.get("data")
        return None

    def get_stale(self, key):
        record = self.cache.get(key)
        if not isinstance(record, dict):
            return None
        return record.get("data")

    def get_record(self, key):
        record = self.cache.get(key)
        if not isinstance(record, dict):
            return None
        return dict(record)
        
    def set(self, key, data, ttl_seconds: int = None):
        now_ts = time.time()
        if ttl_seconds is not None:
            ttl = max(int(ttl_seconds), 1)
            self.cache[key] = {"expires_at": now_ts + ttl, "stored_at": now_ts, "data": data}
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            self.cache[key] = {"date": today, "stored_at": now_ts, "data": data}
        self._flush()

    def set_ttl(self, key, data, ttl_seconds: int):
        now_ts = time.time()
        ttl = max(int(ttl_seconds), 1)
        self.cache[key] = {"expires_at": now_ts + ttl, "stored_at": now_ts, "data": data}
        self._flush()

    def _flush(self):
        with open(self.filepath, 'w') as f:
            json.dump(self.cache, f, indent=4)

class PortfolioDB:
    """本地账本缓存，防止系统重启后失忆"""
    def __init__(self, filepath="portfolio_state.json"):
        self.filepath = filepath
        
    def load_state(self, default_cash, default_positions):
        if os.path.exists(self.filepath):
            logger.info(f"💾 [持久化] 发现本地账本 {self.filepath}，正在恢复昨天的记忆...")
            try:
                with open(self.filepath, 'r') as f:
                    state = json.load(f)
                    return state.get("cash", default_cash), state.get("positions", default_positions)
            except Exception as e:
                logger.warning(f"⚠️ 读取本地账本失败: {e}，将使用初始资金。")
        else:
            logger.info("💾 [持久化] 未找到历史账本，将以初始资金启动新账户。")
        return default_cash, default_positions
        
    def save_state(self, cash, positions):
        state = {"cash": cash, "positions": positions}
        with open(self.filepath, 'w') as f:
            json.dump(state, f, indent=4)
        logger.info(f"💾 [持久化] 账本已安全保存至 {self.filepath}，明天见！")
