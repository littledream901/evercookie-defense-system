import sys
import time
sys.path.insert(0, r'E:\Python\evercookie-defense-system\Evercookie Defense System V2')
from fangyu_template_migrator import OnePanelAPIClient

# 配置
panel_url = 'http://8.222.215.34:38908'
api_key = 'LmabzS0lsmWIWCMn'
container_id = '1Panel-openresty-Srsk'
domain = 'wayaffair.shop'

# 上传文件（带重试）
client = OnePanelAPIClient(panel_url, api_key)
local_path = r'E:\Python\evercookie-defense-system\Evercookie Defense System V2\adapters\nginx-lua\defense.lua'
container_path = f'/www/sites/{domain}/lua/defense.lua'

print(f'上传 {local_path} 到 {container_path}...')

max_retries = 3
for attempt in range(max_retries):
    try:
        result = client.upload_file_to_container(container_id, local_path, container_path)
        print(f'上传结果: {result}')
        if result:
            print('✅ 上传成功')
            break
    except Exception as e:
        print(f'❌ 尝试 {attempt + 1}/{max_retries} 失败: {e}')
        if attempt < max_retries - 1:
            print('等待 2 秒后重试...')
            time.sleep(2)
        else:
            print('上传失败，请检查网络连接')
