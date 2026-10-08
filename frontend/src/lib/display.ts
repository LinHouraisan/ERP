export const labels: Record<string, string> = {
  REQUESTED: '待审批', IN_TRANSIT: '调拨在途', DISCREPANCY: '收货差异待核查', CLOSED_LOSS: '损失已核实结案', TRANSFERRED: '已调往其他门店', LOST: '短少已记录',
  PROCESSING: '处理中', NEEDS_ATTENTION: '异常待处理', COMPLETED_WITH_ADJUSTMENTS: '已完成（含售后或调整）', TIMING_DIFFERENCE: '分期 / 账期差异', TIMING: '到账时间差异', AMOUNT: '金额差异', ADJUSTMENT: '收益调整',
  PLAN: '套餐业务', FAULT: '故障服务', OTHER: '其他咨询', WAITING: '等待中', CALLED: '已叫号', SERVING: '服务中', DONE: '已完成', MISSED: '已过号', CANCELLED: '已取消',
  ACTIVE: '接待中', ENDED: '接待结束', DRAFT: '草稿', READY: '待提交', SUBMITTING: '正在提交，需核对', SUBMITTED: '外部处理中', UNKNOWN: '结果未知，请核对', SUCCESS: '办理成功', FAILED: '失败',
  PASS: '规则通过', NEEDS_REVIEW: '需要人工复核', BLOCKED: '规则阻断', CONFIRM: '人工确认', REJECT: '人工驳回', REVISE: '修订重检',
  OPTIONS: '可选方案', KEEP_CURRENT: '建议保留当前套餐', NO_MATCH: '暂无匹配方案', NEEDS_INFO: '资料不足，请补齐', SERVICE_TASK: '请进入服务任务',
  OPEN: '待处理', IN_PROGRESS: '处理中', CLOSED: '已关闭', PROPOSED: '建议草稿', APPROVED: '已审核', VERIFIED: '已验证', REJECTED: '已驳回',
  PUBLISHED: '已发布', RUNNING: '运行中', SUCCEEDED: '辅助完成', INTERRUPTED: '已中断', COMPLETED: '批次完成', PENDING: '待运行',
  GOODS: '实物商品', PACKAGE: '通信套餐', SERVICE: '服务', QUANTITY: '数量管理', SERIAL: '序列号管理', NONE: '无需出库',
  PARTIAL: '部分收货', RECEIVED: '收货完成', AVAILABLE: '可用', RESERVED: '已占用', SHIPPED: '已出库', CONFIRMED: '已确认',
  APPOINTED: '已预约待派工', DISPATCHED: '已派工', ACCEPTED: '已接单', MATERIALS_READY: '已领料', ON_SITE: '已到场', INSTALLED: '已安装待验收',
  SALE: '销售收益', TELECOM: '通信酬金', INSTALLATION: '安装收益', MATCHED: '金额匹配', AMOUNT_MISMATCH: '金额差异', MISSING_BILL: '缺外部账单', MISSING_INTERNAL: '缺内部台账',
  OPERATING: '经营类', COLLECTION: '代收款', DEPOSIT: '押金', CASH: '现金', CARD: '银行卡', WECHAT: '微信', ALIPAY: '支付宝',
  SOURCE_COMPLETE: '业务交付完成', BILL_MATCHED: '账单匹配并到账', STAFF: '店员', MANAGER: '店长', ADMIN: '管理员', WAREHOUSE: '仓库', INSTALLER: '装维', FINANCE: '财务',
};
export const label = (value: string) => labels[value] || value;
export const date = (value: string | null | undefined) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '—';
export const money = (value: string | null | undefined) => value == null ? '未知' : `${value} 元`;
export const categories = ['PLAN','FAULT','OTHER'].map(value => ({ value, label: label(value) }));
