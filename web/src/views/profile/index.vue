<template>
  <CommonPage title="个人中心" subtitle="查看账号信息、修改密码">
    <n-grid :cols="2" x-gap="16">
      <n-gi>
        <n-card title="账号信息" :bordered="false">
          <n-descriptions :column="1" bordered label-placement="left">
            <n-descriptions-item label="用户名">{{ user?.username }}</n-descriptions-item>
            <n-descriptions-item label="邮箱">{{ user?.email }}</n-descriptions-item>
            <n-descriptions-item label="显示名">{{ user?.display_name }}</n-descriptions-item>
            <n-descriptions-item label="状态">{{ user?.status }}</n-descriptions-item>
            <n-descriptions-item label="角色">
              <n-space>
                <n-tag v-for="r in userStore.roles" :key="r">{{ r }}</n-tag>
              </n-space>
            </n-descriptions-item>
          </n-descriptions>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="修改密码" :bordered="false">
          <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
            <n-form-item label="当前密码" path="old_password">
              <n-input v-model:value="form.old_password" type="password" show-password-on="click" />
            </n-form-item>
            <n-form-item label="新密码" path="new_password">
              <n-input v-model:value="form.new_password" type="password" show-password-on="click" />
            </n-form-item>
            <n-form-item label="确认新密码" path="confirm">
              <n-input v-model:value="form.confirm" type="password" show-password-on="click" />
            </n-form-item>
            <n-button type="primary" :loading="saving" block @click="onSubmit">提交</n-button>
          </n-form>
        </n-card>
      </n-gi>
    </n-grid>
  </CommonPage>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import CommonPage from '@/components/CommonPage.vue'
import { useUserStore } from '@/store/user'
import { authApi } from '@/api/auth'

const message = useMessage()
const userStore = useUserStore()
const user = computed(() => userStore.userInfo)

const saving = ref(false)
const formRef = ref(null)
const form = reactive({ old_password: '', new_password: '', confirm: '' })
const rules = {
  old_password: { required: true, message: '请输入当前密码' },
  new_password: { required: true, message: '请输入新密码', min: 8 },
  confirm: {
    required: true,
    validator: (_, value) => value === form.new_password || new Error('两次输入不一致'),
    trigger: ['blur', 'input'],
  },
}

async function onSubmit() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    await authApi.changePassword({ old_password: form.old_password, new_password: form.new_password })
    message.success('密码已更新，请重新登录')
    await userStore.logout()
    window.location.href = '/login'
  } catch (e) {
    message.error(e.message || '修改失败')
  } finally {
    saving.value = false
  }
}
</script>
