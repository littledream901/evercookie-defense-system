<!-- 个人中心 -->
<template>
  <div class="art-full-height">
    <div class="mb-4">
      <h2 class="text-lg font-medium text-g-900">个人中心</h2>
      <p class="mt-1 text-sm text-g-600">查看账号信息、修改密码、管理 API Key</p>
    </div>

    <ElTabs v-model="activeTab" type="card">
      <!-- 账号信息 Tab -->
      <ElTabPane label="账号信息" name="account">
        <ElRow :gutter="16">
          <!-- 账号信息 -->
          <ElCol :span="10">
            <ElCard shadow="never" header="账号信息">
              <ElDescriptions :column="1" border>
                <ElDescriptionsItem label="用户名">{{ user.userName }}</ElDescriptionsItem>
                <ElDescriptionsItem label="邮箱">{{ user.email }}</ElDescriptionsItem>
                <ElDescriptionsItem label="显示名">{{ user.displayName || '-' }}</ElDescriptionsItem>
                <ElDescriptionsItem label="状态">
                  <ElTag :type="user.status === 'active' ? 'success' : 'warning'" size="small">
                    {{ user.status === 'active' ? '正常' : user.status }}
                  </ElTag>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="角色">
                  <ElTag v-for="r in user.roles" :key="r" size="small" class="mr-1 mb-1">{{ r }}</ElTag>
                </ElDescriptionsItem>
              </ElDescriptions>
            </ElCard>
          </ElCol>

          <!-- 修改密码 -->
          <ElCol :span="14">
            <ElCard shadow="never" header="修改密码">
              <ElForm ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="110px">
                <ElFormItem label="当前密码" prop="old_password">
                  <ElInput v-model="pwdForm.old_password" type="password" show-password />
                </ElFormItem>
                <ElFormItem label="新密码" prop="new_password">
                  <ElInput v-model="pwdForm.new_password" type="password" show-password />
                </ElFormItem>
                <ElFormItem label="确认新密码" prop="confirm_password">
                  <ElInput v-model="pwdForm.confirm_password" type="password" show-password />
                </ElFormItem>
                <ElFormItem>
                  <ElButton type="primary" :loading="saving" @click="submitPassword">修改密码</ElButton>
                  <ElButton @click="resetPwdForm">重置</ElButton>
                </ElFormItem>
              </ElForm>
            </ElCard>
          </ElCol>
        </ElRow>
      </ElTabPane>

      <!-- API Key Tab -->
      <ElTabPane label="API Keys" name="apikeys">
        <ApiKeyManagement />
      </ElTabPane>
    </ElTabs>
  </div>
</template>
<script setup lang="ts">
  import { useUserStore } from '@/store/modules/user'
  import { fetchChangePassword } from '@/api/auth'
  import type { FormInstance, FormRules } from 'element-plus'
  import ApiKeyManagement from '@/components/ApiKeyManagement.vue'

  defineOptions({ name: 'FangyuProfile' })

  const userStore = useUserStore()
  const user = computed(() => userStore.getUserInfo)

  const activeTab = ref('account')
  const saving = ref(false)
  const pwdFormRef = ref<FormInstance>()
  const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })

  const pwdRules: FormRules = {
    old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
    new_password: [
      { required: true, message: '请输入新密码', trigger: 'blur' },
      { min: 8, message: '密码至少 8 位', trigger: 'blur' }
    ],
    confirm_password: [
      { required: true, message: '请确认新密码', trigger: 'blur' },
      {
        validator: (_rule: any, value: string, callback: (e?: Error) => void) => {
          value !== pwdForm.new_password
            ? callback(new Error('两次密码不一致'))
            : callback()
        },
        trigger: 'blur'
      }
    ]
  }

  async function submitPassword() {
    const valid = await pwdFormRef.value?.validate().catch(() => false)
    if (!valid) return
    saving.value = true
    try {
      await fetchChangePassword({ old_password: pwdForm.old_password, new_password: pwdForm.new_password })
      ElMessage.success('密码修改成功，下次登录生效')
      resetPwdForm()
    } finally {
      saving.value = false
    }
  }

  function resetPwdForm() {
    pwdFormRef.value?.resetFields()
  }
</script>
