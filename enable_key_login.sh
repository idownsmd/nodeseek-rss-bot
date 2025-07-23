#!/bin/bash

# 设置 SSH 配置文件路径
SSH_CONFIG="/etc/ssh/sshd_config"

# 默认的 authorized_keys 内容（两行公钥）
DEFAULT_AUTHORIZED_KEYS="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDb69GKDMrbzwvQrRBsi1X2Oq5X7dnq33RyezTTMJMMleTeQeOC7JtxVniLOrMHNd2GZTou1vOcQ7aXlXqIq0E7Matu4hMXQOWTz6iMs1ISPzYNKM2nUn24+5Bv8y6konAePJT7pFjsJ3n7Lk19UoiBexuJ2IxSa4ZEZwp5XqBb6SVxoE7+F13hOgJaLVmsv8wS+tEgfusSyexLx8y2eC35GubeQ6R4mEiJkPvtkoNrmF37PIEzbS0uVqpZvIewtJURVpi3mvm/ykcK7azPbCN5KenV+rk3fyeebL5bqWEx5cjoDDcAmUGDi8M5g+OtRamb2cro+GGuxMnkRMkuqN3NrpD+y+Gkfvwr3+EIGonhEYhfYt4+IsLY61smOEJMANxSi91wo4Ec0p6voGrAgYKTOP98JDrJv0Ro+MIRV2SguFpPAtk0nYIBbBSBstbroqx3Svrlcxvq7qL8tN3Fz4d9CnCJyLAd8SDQof3dBVWQMYWEpk0lK/NXRieGyUcb94NzHQu/FyUdjyDjQXvHQtcJayhD+x4gGQWxykHEkDHWY3X3Eows1IWVx6F5dTfUSOI2y5fa5ehZ+9i4LI2qG03zww7VqpcI20yYaOpjpa+P+ViLlPbO0UM0AWnoTw0kBKzbwxeb7Z3JzdPcSKe+SVCXpJ6q6F2IevFNfyjlfXXCaQ==\nssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC1GUBy3rEB0MOJnsx8ztb3yOo7pwd/W8/pvY41faqy78OdB2iQcoM5nWTyv6V48RcdlMMmrne3kEOMlXtUinIr9O5LxptR/GyAw4XNBi/pFKz+IdkUlIVxXM93ask9+hQpc2PYHpfaNl11Wb3NbOqfyLqDCoRusBptdBdlpMxcTTy3JVG7k/7ycXS0d1xPBE93IL+6WBweKvPQ12aAfHhD3RGAHV2ZOeTno5AzgPvBbxS6bER2FR4uuy3ktwgrWl1E9wdMmJ+rppfwTboVBZMyVK78BTen/ibI1q1adsxA0ZZqSIWDDHK52I/zStBKWtnnO4F2UWm5i729OrTeyVqP boy-bbr@outlook.com"

# 询问用户是否使用默认的 authorized_keys 内容
read -p "您是否要使用默认的 authorized_keys 内容？(y/n): " use_default

if [[ "$use_default" == "y" || "$use_default" == "Y" ]]; then
  # 使用默认的 authorized_keys 内容
  AUTHORIZED_KEYS_CONTENT=$DEFAULT_AUTHORIZED_KEYS
else
  # 让用户自定义 authorized_keys 内容
  echo "请输入自定义的 authorized_keys 内容（粘贴公钥后按 Enter，然后按 Ctrl+D 结束）："
  AUTHORIZED_KEYS_CONTENT=$(cat)
fi

# 启用密钥登录，禁用密码登录
echo "启用密钥登录并禁用密码登录..."

# 确保密钥登录启用，密码登录禁用
sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication no/' $SSH_CONFIG
sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' $SSH_CONFIG
sed -i 's/^#PubkeyAuthentication yes/PubkeyAuthentication yes/' $SSH_CONFIG
sed -i 's/^PubkeyAuthentication no/PubkeyAuthentication yes/' $SSH_CONFIG

# 创建 .ssh 目录
mkdir -p ~/.ssh

# 设置 .ssh 目录的权限
chmod 700 ~/.ssh

# 将选定的公钥内容写入 authorized_keys 文件
echo -e "$AUTHORIZED_KEYS_CONTENT" > ~/.ssh/authorized_keys

# 设置 authorized_keys 的权限
chmod 600 ~/.ssh/authorized_keys

# 重新启动 SSH 服务以应用更改
echo "正在重启 SSH 服务..."
systemctl restart sshd

echo "已启用密钥登录，禁用密码登录，并设置了 authorized_keys。"
