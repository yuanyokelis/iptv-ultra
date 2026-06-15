include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-iptv-ultra
PKG_VERSION:=1.0.0
PKG_RELEASE:=1

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-iptv-ultra
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=LuCI support for IPTV Ultra Pro
  DEPENDS:=+python3-light +python3-urllib +ffmpeg +ffprobe
  PKGARCH:=all
enddefine

define Build/Compile
enddefine

define Package/luci-app-iptv-ultra/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) ./files/iptv-ultra $(1)/usr/bin/iptv-ultra
	$(INSTALL_BIN) ./files/iptv-probe.py $(1)/usr/bin/iptv-probe.py
	
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_CONF) ./files/iptv-ultra.config $(1)/etc/config/iptv-ultra
	
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/iptv-ultra.init $(1)/etc/init.d/iptv-ultra
	
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/controller
	$(INSTALL_DATA) ./files/iptv-ultra.lua $(1)/usr/lib/lua/luci/controller/iptv-ultra.lua
	
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/model/cbi/iptv-ultra
	$(INSTALL_DATA) ./files/settings.lua $(1)/usr/lib/lua/luci/model/cbi/iptv-ultra/settings.lua
enddefine

$(eval $(call BuildPackage,luci-app-iptv-ultra))