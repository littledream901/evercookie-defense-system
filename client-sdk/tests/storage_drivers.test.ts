/**
 * SDK 存储驱动行为测试
 * 
 * 测试所有存储驱动的实际行为（get/set/remove/isAvailable）。
 * jsdom 环境支持 localStorage、sessionStorage、cookie、window.name。
 * IndexedDB 需要 fake-indexeddb 库，暂不测试（已在生产环境验证）。
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { localStorageDriver } from '../src/storage/local_storage'
import { cookieDriver } from '../src/storage/cookie'
import { windowNameDriver } from '../src/storage/window_name'

describe('LocalStorage Driver', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('isAvailable returns true in jsdom', () => {
    expect(localStorageDriver.isAvailable()).toBe(true)
  })

  it('set and get roundtrip', () => {
    const key = 'test_fp'
    const value = 'abc123def456'
    
    localStorageDriver.set(key, value)
    const retrieved = localStorageDriver.get(key)
    
    expect(retrieved).toBe(value)
  })

  it('get returns null for missing key', () => {
    expect(localStorageDriver.get('nonexistent')).toBeNull()
  })

  it('remove deletes key', () => {
    const key = 'temp'
    localStorageDriver.set(key, 'value')
    expect(localStorageDriver.get(key)).toBe('value')
    
    localStorageDriver.remove(key)
    expect(localStorageDriver.get(key)).toBeNull()
  })

  it('handles special characters', () => {
    const key = 'fp_with_特殊字符'
    const value = 'value=with&special?chars'
    
    localStorageDriver.set(key, value)
    expect(localStorageDriver.get(key)).toBe(value)
  })
})

describe('Cookie Driver', () => {
  beforeEach(() => {
    // 清理所有 cookie
    document.cookie.split(';').forEach(c => {
      const key = c.split('=')[0]?.trim()
      if (key) {
        document.cookie = `${key}=; path=/; max-age=0`
      }
    })
  })

  it('isAvailable returns true in jsdom', () => {
    expect(cookieDriver.isAvailable()).toBe(true)
  })

  it('set and get roundtrip', () => {
    const key = 'test_cookie'
    const value = 'cookie_value_123'
    
    cookieDriver.set(key, value)
    const retrieved = cookieDriver.get(key)
    
    expect(retrieved).toBe(value)
  })

  it('get returns null for missing cookie', () => {
    expect(cookieDriver.get('nonexistent_cookie')).toBeNull()
  })

  it('remove deletes cookie', () => {
    const key = 'temp_cookie'
    cookieDriver.set(key, 'value')
    expect(cookieDriver.get(key)).toBe('value')
    
    cookieDriver.remove(key)
    expect(cookieDriver.get(key)).toBeNull()
  })

  it('encodes special characters', () => {
    const key = 'cookie_特殊'
    const value = 'value with spaces & symbols='
    
    cookieDriver.set(key, value)
    expect(cookieDriver.get(key)).toBe(value)
  })
})

describe('WindowName Driver', () => {
  beforeEach(() => {
    window.name = ''
  })

  it('isAvailable returns true in jsdom', () => {
    expect(windowNameDriver.isAvailable()).toBe(true)
  })

  it('set and get roundtrip', () => {
    const key = 'test_wn'
    const value = 'window_name_value'
    
    windowNameDriver.set(key, value)
    const retrieved = windowNameDriver.get(key)
    
    expect(retrieved).toBe(value)
  })

  it('get returns null for missing key', () => {
    expect(windowNameDriver.get('nonexistent')).toBeNull()
  })

  it('remove deletes key', () => {
    const key = 'temp_wn'
    windowNameDriver.set(key, 'value')
    expect(windowNameDriver.get(key)).toBe('value')
    
    windowNameDriver.remove(key)
    expect(windowNameDriver.get(key)).toBeNull()
  })

  it('supports multiple keys in window.name', () => {
    windowNameDriver.set('key1', 'value1')
    windowNameDriver.set('key2', 'value2')
    windowNameDriver.set('key3', 'value3')
    
    expect(windowNameDriver.get('key1')).toBe('value1')
    expect(windowNameDriver.get('key2')).toBe('value2')
    expect(windowNameDriver.get('key3')).toBe('value3')
  })

  it('encodes special characters in window.name', () => {
    const key = 'wn_特殊'
    const value = 'value=with&chars'
    
    windowNameDriver.set(key, value)
    expect(windowNameDriver.get(key)).toBe(value)
  })

  it('formats window.name as key=value pairs', () => {
    windowNameDriver.set('a', '1')
    windowNameDriver.set('b', '2')
    
    // window.name 应该是 URL 编码的 k=v&k=v 格式
    expect(window.name).toContain('=')
    expect(window.name).toContain('&')
  })
})

describe('Storage Driver Contract', () => {
  const drivers = [
    { name: 'localStorage', driver: localStorageDriver },
    { name: 'cookie', driver: cookieDriver },
    { name: 'windowName', driver: windowNameDriver },
  ]

  drivers.forEach(({ name, driver }) => {
    it(`${name} has required methods`, () => {
      expect(typeof driver.isAvailable).toBe('function')
      expect(typeof driver.get).toBe('function')
      expect(typeof driver.set).toBe('function')
      expect(typeof driver.remove).toBe('function')
      expect(driver.name).toBe(name)
    })
  })
})
