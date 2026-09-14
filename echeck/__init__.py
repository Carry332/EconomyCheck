"""财报 Benford 分析工具包。

模块：
  config    路径与运行环境
  cninfo    巨潮资讯网(cninfo)官方披露接口：搜索公司 / 列定期报告 / 下载 PDF
  pdftext   PDF 转文本
  parse     从报告文本中定位三大合并报表并抽取金额
  stats     首位数字分布统计与 Benford 检验
  viz       分布对比图（Pillow）
  pipeline  端到端流程编排（带进度回调与取消）
  gui       tkinter 图形界面
"""

__version__ = "1.0.0"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2026 Carry"
