<template>
  <n-result status="403" title="403 无权访问" description="您没有访问该页面的权限" class="mt-80px">
    <template #footer>
      <n-button @click="$router.replace('/')">返回首页</n-button>
    </template>
  </n-result>
</template>
