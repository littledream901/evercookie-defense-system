# 访问日志详情抽屉 - 迁移脚本
# 用于快速切换新旧版本

# ========================================
# 使用方法：
# 1. 备份并启用新版本：
#    node migrate-detail-drawer.js enable
#
# 2. 回滚到旧版本：
#    node migrate-detail-drawer.js rollback
# ========================================

const fs = require('fs')
const path = require('path')

const BASE_PATH = path.join(__dirname, '../dashboard-ui/src/views/fangyu/access-logs/modules')
const OLD_FILE = path.join(BASE_PATH, 'log-detail-drawer.vue')
const NEW_FILE = path.join(BASE_PATH, 'log-detail-drawer-new.vue')
const BACKUP_FILE = path.join(BASE_PATH, 'log-detail-drawer.bak.vue')

const action = process.argv[2]

function enableNewVersion() {
  console.log('📦 开始迁移到新版本...\n')

  // 1. 检查文件是否存在
  if (!fs.existsSync(OLD_FILE)) {
    console.error('❌ 旧版本文件不存在:', OLD_FILE)
    process.exit(1)
  }

  if (!fs.existsSync(NEW_FILE)) {
    console.error('❌ 新版本文件不存在:', NEW_FILE)
    process.exit(1)
  }

  // 2. 备份旧版本
  console.log('📋 备份旧版本...')
  fs.copyFileSync(OLD_FILE, BACKUP_FILE)
  console.log('✅ 备份完成:', BACKUP_FILE)

  // 3. 删除旧版本
  console.log('\n🗑️  删除旧版本...')
  fs.unlinkSync(OLD_FILE)
  console.log('✅ 删除完成')

  // 4. 重命名新版本
  console.log('\n📝 启用新版本...')
  fs.renameSync(NEW_FILE, OLD_FILE)
  console.log('✅ 重命名完成:', OLD_FILE)

  console.log('\n🎉 迁移成功！')
  console.log('\n📌 请执行以下步骤验证：')
  console.log('   1. 重启开发服务器')
  console.log('   2. 打开访问日志页面')
  console.log('   3. 点击详情按钮测试功能')
  console.log('   4. 验证所有 Tab 页正常')
  console.log('   5. 测试规则明细加载')
  console.log('\n⚠️  如需回滚，执行: node migrate-detail-drawer.js rollback')
}

function rollback() {
  console.log('⏮️  开始回滚到旧版本...\n')

  // 1. 检查备份是否存在
  if (!fs.existsSync(BACKUP_FILE)) {
    console.error('❌ 备份文件不存在，无法回滚')
    process.exit(1)
  }

  // 2. 如果当前文件存在，重命名为 new
  if (fs.existsSync(OLD_FILE)) {
    console.log('📝 保存当前版本为 new...')
    fs.renameSync(OLD_FILE, NEW_FILE)
    console.log('✅ 保存完成')
  }

  // 3. 恢复备份
  console.log('\n📋 恢复备份...')
  fs.copyFileSync(BACKUP_FILE, OLD_FILE)
  console.log('✅ 恢复完成')

  console.log('\n🎉 回滚成功！')
  console.log('⚠️  请重启开发服务器')
}

// 主逻辑
if (action === 'enable') {
  enableNewVersion()
} else if (action === 'rollback') {
  rollback()
} else {
  console.log('📖 使用方法：')
  console.log('   node migrate-detail-drawer.js enable    # 启用新版本')
  console.log('   node migrate-detail-drawer.js rollback  # 回滚到旧版本')
}
