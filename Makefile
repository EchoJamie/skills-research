PYTHON ?= python3
MANAGER := $(PYTHON) scripts/manage.py
RESOURCES ?=
FORCE_ARG := $(if $(filter 1 true yes,$(FORCE)),--force,)

.PHONY: help bootstrap validate test doctor status device-list sync unsync adopt promote qa-link qa-unlink

help:
	@echo "可用命令："
	@echo "  make bootstrap     校验并恢复正式已安装集合"
	@echo "  make validate      校验仓库、Skill 与 Agent"
	@echo "  make test          运行资源管理器测试"
	@echo "  make doctor        检查本机运行条件与安装目录"
	@echo "  make status        查看开发资源和正式集合状态"
	@echo "  make device-list   只读盘点设备已有 Skill 与 Agent"
	@echo "  make sync [FORCE=1] 挂载正式已安装集合"
	@echo '  make unsync RESOURCES="skill:name [agent:name]"'
	@echo '  make adopt RESOURCES="skill:name"  显式纳管一个设备资源'
	@echo '  make promote RESOURCES="skill:name [agent:name]" [FORCE=1]'
	@echo '  make qa-link RESOURCES="skill:name [agent:name]" [FORCE=1]'
	@echo '  make qa-unlink RESOURCES="skill:name [agent:name]"'

bootstrap: doctor sync status device-list

validate:
	@$(MANAGER) validate

test:
	@$(PYTHON) -m unittest discover -s tests -v

doctor:
	@$(MANAGER) doctor

status:
	@$(MANAGER) status

device-list:
	@$(MANAGER) device-list

sync:
	@$(MANAGER) sync $(FORCE_ARG)

unsync:
	@$(MANAGER) unsync $(RESOURCES)

adopt:
	@$(MANAGER) adopt $(RESOURCES)

promote:
	@$(MANAGER) promote $(RESOURCES) $(FORCE_ARG)

qa-link:
	@$(MANAGER) qa-link $(RESOURCES) $(FORCE_ARG)

qa-unlink:
	@$(MANAGER) qa-unlink $(RESOURCES)
