#!/bin/sh
# Отладка issue #1: радио модема падает на ассерте RFLM и уносит с собой Wi-Fi,
# потому что прошивка WCN3990 живёт на том же DSP. Режим online сохраняется в NV,
# поэтому гасим радио на каждой загрузке, пока причина не найдена.
i=0
while [ $i -lt 45 ]; do
	if qmicli -d qrtr://0 --dms-set-operating-mode=persistent-low-power 2>&1; then
		exit 0
	fi
	i=$((i + 1))
	sleep 2
done
exit 0
