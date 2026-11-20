import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  createUser as createUserApi,
  grantBalance as grantBalanceApi,
  listUsers,
} from '../api/admin'
import { errorMessage } from '../api/errors'
import type {
  AdminUser,
  CreateUserRequest,
  GrantBalanceRequest,
} from '../types/account'

export const useAdminStore = defineStore('admin', () => {
  const users = ref<AdminUser[]>([])
  const loading = ref(false)
  const error = ref('')

  async function fetchUsers() {
    loading.value = true
    error.value = ''
    try {
      const list = await listUsers()
      users.value = Array.isArray(list) ? list : []
    } catch (err) {
      error.value = errorMessage(err, '用户列表加载失败')
    } finally {
      loading.value = false
    }
  }

  async function createUser(payload: CreateUserRequest) {
    const user = await createUserApi(payload)
    users.value = [user, ...users.value.filter((item) => item.id !== user.id)]
    return user
  }

  async function grantBalance(userId: number, payload: GrantBalanceRequest) {
    const user = await grantBalanceApi(userId, payload)
    const index = users.value.findIndex((item) => item.id === user.id)
    if (index >= 0) users.value.splice(index, 1, user)
    return user
  }

  return { users, loading, error, fetchUsers, createUser, grantBalance }
})
