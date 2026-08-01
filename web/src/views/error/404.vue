<template>
  <n-result status="404" title="404 页面不存在" description="您访问的页面已被移除或从未存在" class="mt-80px">
    <template #footer>
      <n-button @click="$router.replace('/')">返回首页</n-button>
    </template>
  </n-result>
</template>
