import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import type { PropsWithChildren } from 'react'

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#176b4d',
          colorInfo: '#176b4d',
          colorSuccess: '#176b4d',
          colorText: '#172033',
          colorTextSecondary: '#5b6473',
          colorBgBase: '#f5f7f7',
          colorBorder: '#d7dddc',
          borderRadius: 8,
          fontFamily:
            '"Noto Sans SC", "Microsoft YaHei", ui-sans-serif, system-ui, sans-serif',
        },
        components: {
          Button: {
            controlHeight: 42,
          },
        },
      }}
    >
      {children}
    </ConfigProvider>
  )
}
