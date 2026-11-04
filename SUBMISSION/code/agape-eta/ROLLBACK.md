# agape-eta rollback (this node)
systemctl --user disable --now agape-eta.timer
rm -f ~/.config/systemd/user/agape-eta.service ~/.config/systemd/user/agape-eta.timer
systemctl --user daemon-reload
rm -rf ~/agape-eta
Nothing else on this node was changed.
