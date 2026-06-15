include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-iptv-ultra
PKG_VERSION:=2.0.0
PKG_RELEASE:=1
PKG_LICENSE:=MIT
PKG_MAINTAINER:=IPTV Ultra Team

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-iptv-ultra
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=IPTV Ultra Pro - Smart IPTV source optimizer
  URL:=https://github.com/yuanyokelis/iptv-ultra
  DEPENDS:=+python3-light +python3-urllib +ffmpeg +ffprobe +luci-base +luci-compat
  PKGARCH:=all
  PROVIDES:=luci-app-iptv-ultra
endef

define Package/luci-app-iptv-ultra/description
  Automatic IPTV source fetching, FFmpeg-based quality testing,
  intelligent aggregation, and optimized playlist generation for OpenWrt.
  Supports TVBox / 影视仓 subscription.
endef

define Build/Compile
endef

define Package/luci-app-iptv-ultra/install
	# Main control script
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) ./files/usr/bin/iptv-ultra $(1)/usr/bin/iptv-ultra
	$(INSTALL_BIN) ./files/usr/bin/iptv-probe.py $(1)/usr/bin/iptv-probe.py

	# UCI config
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_CONF) ./files/etc/config/iptv-ultra $(1)/etc/config/iptv-ultra

	# Init script
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/etc/init.d/iptv-ultra $(1)/etc/init.d/iptv-ultra

	# LuCI controller
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/controller
	$(INSTALL_DATA) ./files/usr/lib/lua/luci/controller/iptv-ultra.lua $(1)/usr/lib/lua/luci/controller/iptv-ultra.lua

	# LuCI CBI model
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/model/cbi/iptv-ultra
	$(INSTALL_DATA) ./files/usr/lib/lua/luci/model/cbi/iptv-ultra/settings.lua $(1)/usr/lib/lua/luci/model/cbi/iptv-ultra/settings.lua

	# WWW directory for HTTP output
	$(INSTALL_DIR) $(1)/www/iptv

	# Post-install / post-remove scripts for APK compatibility
	$(INSTALL_DIR) $(1)/usr/lib/apk/triggers
endef

define Package/luci-app-iptv-ultra/conffiles
/etc/config/iptv-ultra
endef

# APK package metadata (OpenWrt 24+)
ifeq ($(APK),y)
  define Package/luci-app-iptv-ultra/apk
    PROVIDES:=luci-app-iptv-ultra
    VERSION:=$(PKG_VERSION)-r$(PKG_RELEASE)
  endef
endif

$(eval $(call BuildPackage,luci-app-iptv-ultra))
