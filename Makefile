# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 white-toolbelt contributors

.PHONY: install setup

install:
	./install.sh

USER := $(shell whoami)

setup:
	sudo usermod --add-subuids 100000-165535 $(USER)
	sudo usermod --add-subgids 100000-165535 $(USER)
	sudo chmod 1777 /tmp
	loginctl enable-linger
