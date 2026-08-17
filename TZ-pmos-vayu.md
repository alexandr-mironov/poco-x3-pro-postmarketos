# ТЗ: установка postmarketOS (Phosh) на POCO X3 Pro `vayu` через pmbootstrap

Документ предназначен для агента (Claude Code), запускаемого на домашнем сервере.
Человек-оператор (владелец) присутствует физически и выполняет действия с телефоном.

> **Ревизия от 2026-08-17.** Документ переписан по факту прохождения Фаз 0–3 на реальном
> сервере и реальном телефоне. Всё, что помечено ✅ ПРОВЕРЕНО, подтверждено выводом команд,
> а не предположением. Исходная редакция содержала несколько неверных допущений — они
> перечислены в разделе 7.

---

## 0. Контекст и факты об устройстве

### Телефон

- Устройство: **Xiaomi POCO X3 Pro**, кодовое имя **`vayu`**, вариант `vayu_global`,
  маркетинговая модель `M2102J20SG`. ✅ ПРОВЕРЕНО (`adb shell getprop ro.product.device`)
- SoC: Qualcomm **sm8150** (Snapdragon 860). Порт в postmarketOS — категория testing
  (mainline-ядро `linux-postmarketos-qcom-sm8150`).
- Накопитель 128 ГБ; `/data` занято 15 ГБ из 107 ГБ. ✅ ПРОВЕРЕНО
- **Текущая прошивка — не сток, а `xiaomi.eu` MIUI 14.0.3** (`V14.0.3.0.TJUMIXM`,
  Android 13, сборка от 2023-05-07). Опознаётся по `ro.product.mod_device = vayu_xiaomieu_global`.
  ✅ ПРОВЕРЕНО
- Не A/B-устройство: `fastboot getvar current-slot` → `Variable Not found`. Есть отдельный
  раздел `recovery`. ✅ ПРОВЕРЕНО
- Root **отсутствует** — ни `su`, ни Magisk/KernelSU/APatch среди установленных пакетов.
  ✅ ПРОВЕРЕНО
- Два пользователя Android: `0` (основной) и `10` (`security space` = второе пространство).
  ✅ ПРОВЕРЕНО

- **Панель дисплея: Huaxing (контроллер NT36672C).** Подтверждено из bugreport:
  `MDPPLATFORM_PANEL_HUAXING_NT36672C_J20S_LCD_VIDEO`, внутреннее имя `dsi_j20s`.
  → В `pmbootstrap init` выбирать ядро варианта **`huaxing`**
  (подпакет `device-xiaomi-vayu-kernel-huaxing`). Вариант `tianma` НЕ использовать — чёрный экран.
  Оба варианта существуют в `pmaports/device/testing/device-xiaomi-vayu/APKBUILD`. ✅ ПРОВЕРЕНО

### ⚠️ Загрузчик: свойствам Android верить нельзя

**Загрузчик РАЗБЛОКИРОВАН.** ✅ ПРОВЕРЕНО — `fastboot getvar unlocked` → `unlocked: yes`.
Этап Mi Unlock пропускается.

Но есть ловушка, на которой можно потерять неделю:

```
# Что говорит Android (ЛОЖЬ — xiaomi.eu подделывает эти свойства ради
# прохождения SafetyNet / Play Integrity, чтобы работали банковские приложения):
ro.boot.flash.locked      = 1
ro.boot.verifiedbootstate = green

# Что говорит сам загрузчик (ПРАВДА):
fastboot getvar unlocked  -> unlocked: yes
```

**Правило: состояние загрузчика определяется ТОЛЬКО через `fastboot getvar unlocked`.**
Любые `getprop ro.boot.*` на кастомной прошивке недостоверны.

Косвенный признак подделки, заметный и без fastboot: `ro.build.fingerprint` содержит
`RKQ1.200826.002`, а `ro.build.display.id` — `TKQ1.221013.002`. У честной стоковой сборки
они совпадают.

### Прочее

- Целевой интерфейс: **Phosh**.
- Хост сборки: **Oracle Linux 9.4**, x86_64, физическая машина (не VM).
  Ядро — **UEK `5.15.0-301.163.5.2.el9uek`**, а НЕ RHCK (исходное ТЗ утверждало обратное).
  На работу pmbootstrap это не повлияло. ✅ ПРОВЕРЕНО
- Доступ: SSH `node1@192.168.1.248`, ключ `~/.ssh/htrex_servers_ed25519`.

## 1. Разделение ответственности

**Агент (автономно по SSH на сервере):**
- Валидация окружения, установка зависимостей и pmbootstrap, конфигурация, сборка образа,
  запуск команд прошивки.

**Человек (физически у сервера и телефона):**
- Подключить телефон кабелем к USB сервера.
- Включить отладку по USB и подтвердить RSA-запрос на экране.
- Дать явное подтверждение перед разрушающей прошивкой.
- Смотреть на экран телефона при первой загрузке.

Агент НЕ может подключить телефон и нажать кнопки — на этих шагах он останавливается и ждёт человека.

**Что агент может делать без человека:** перевод телефона в fastboot не требует зажимания
кнопок — достаточно `adb reboot bootloader`. Обратно — `fastboot reboot`. ✅ ПРОВЕРЕНО

## 2. Ключевые риски и ПРАВИЛО ОТКАТА

Oracle Linux не входит в официально поддерживаемые pmbootstrap хосты. Итог по рискам:

| Риск из исходного ТЗ | Фактический статус |
|---|---|
| SELinux (enforcing) блокирует chroot/mount | ❌ не подтвердился — создание chroot и монтирование прошли в enforcing, `setenforce 0` НЕ понадобился |
| binfmt_misc + qemu-user нужны для aarch64 | ❌ не проблема — pmbootstrap ставит `qemu-aarch64` внутрь своего Alpine-chroot и сам делает `Register qemu binfmt (aarch64)`. Хостовый `qemu-user-static` не нужен (и в репах OL9 его нет) |
| pmbootstrap не запакован в репах OL | ✅ подтвердился — ставится из git, см. Фазу 2 |

**Правило отката:** если в Фазе 0–2 обнаружены блокеры, которые не устраняются разумными
усилиями — НЕ упорствовать на Oracle Linux. Зафиксировать проблему в отчёте и сообщить
оператору: fallback-план — загрузочная флешка с Ubuntu на ноутбуке, прошивка оттуда.
Собранные артефакты при этом не нужны.

## 3. Обязательные гарды безопасности

- Ни одной разрушающей команды `fastboot`/`pmbootstrap flasher` БЕЗ явного подтверждения
  оператора в текущей сессии.
- Перед прошивкой обязательно проверить: `fastboot getvar unlocked` = `yes` и что выбрано
  ядро `huaxing`.
- Если для сборки SELinux переводится в permissive (`setenforce 0`) — это фиксируется в
  отчёте, и после завершения работ SELinux возвращается в прежний режим (`setenforce 1`).
  **На практике не потребовалось.**
- Пароли НЕ передавать аргументом командной строки (видно в `ps` и в логах). Передавать
  через stdin из файла с `umask 077`, файл удалять после использования.
- Работать в пределах рабочей папки проекта и служебных каталогов pmbootstrap. Не трогать
  посторонние данные сервера.
- Весь вывод команд, где есть ошибки, сохранять и показывать оператору, а не «глотать».

---

## Фаза 0 — Валидация окружения (СНАЧАЛА; затем СТОП на ревью)

Собрать данные и вывести отчёт. НЕ устанавливать ничего на этом шаге.

```bash
echo "=== arch/os ==="; uname -m; uname -r; grep -E 'PRETTY_NAME|VERSION_ID' /etc/os-release
echo "=== selinux ==="; getenforce; sestatus 2>/dev/null | head
echo "=== deps ==="; python3 --version; git --version; openssl version
echo "=== binfmt ==="; ls /proc/sys/fs/binfmt_misc/ 2>/dev/null | head
echo "=== loop ==="; ls -l /dev/loop-control 2>/dev/null; lsmod | grep -i loop
echo "=== disk ==="; df -h $HOME /var /tmp
echo "=== epel ==="; dnf repolist 2>/dev/null | grep -i epel || echo "EPEL не подключён"
echo "=== usb tools ==="; which fastboot adb 2>/dev/null || echo "android-tools не установлены"
echo "=== sudo ==="; sudo -n true && echo "sudo NOPASSWD ok" || echo "sudo требует пароль"
```

Критерии готовности к следующей фазе:
- Архитектура x86_64 (или aarch64 — тоже допустимо, тогда кросс-эмуляция не нужна).
- Свободно ≥ 25 ГБ на разделе с `$HOME`.
- **python3 ≥ 3.10** (см. Фазу 2 — это жёсткое требование pmbootstrap 3.x).
- git, openssl присутствуют.
- **`sudo -n` работает без пароля.** Без этого агент не сможет ничего: ни ставить пакеты,
  ни регистрировать binfmt, ни звать fastboot. Оператор выдаёт NOPASSWD сам:
  ```bash
  echo 'node1 ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/99-node1-pmb
  sudo chmod 440 /etc/sudoers.d/99-node1-pmb
  ```
  После завершения работ файл удалить.

**СТОП.** Вывести отчёт оператору. Если видны блокеры — применить Правило отката (раздел 2).

### Результат прогона на этом сервере ✅

| Проверка | Факт |
|---|---|
| Архитектура / ОС | x86_64, Oracle Linux 9.4, физическая машина |
| Ядро | `5.15.0-301.163.5.2.el9uek` (UEK) |
| Диск | `/home` 289 ГБ свободно |
| Python (штатный) | 3.9.18 → **недостаточно**, поставлен `python3.11` |
| SELinux | Enforcing (менять не потребовалось) |
| binfmt_misc | смонтирован, обработчиков нет (pmbootstrap регистрирует свои) |
| EPEL | подключён |
| `qemu-user-static` | **отсутствует во всех репах OL9** (и не нужен) |
| USB | реальные корневые хабы 2.0/3.0 |

## Фаза 1 — Зависимости

```bash
sudo dnf install -y --disablerepo="gitlab*" --disablerepo="runner*" \
    python3.11 python3.11-pip android-tools
```

⚠️ **`--disablerepo` обязателен на этом сервере.** Сторонние репозитории
`gitlab_gitlab-ce*` и `runner_gitlab-runner` отдают `repomd.xml GPG signature verification
error: Bad GPG signature` и роняют ЛЮБОЙ `dnf install`. Конфиги этих репозиториев не
трогать — это отдельная проблема сервера, не относящаяся к задаче.

⚠️ Побочный эффект: dnf по зависимостям обновит `openssl` (3.0.7 → 3.5.5) и `sqlite-libs`.

### udev-правила (обязательно)

Без них `adb` видит устройство как `no permissions`, а `fastboot` требует sudo:

```bash
sudo tee /etc/udev/rules.d/51-android.rules <<'RULES'
SUBSYSTEM=="usb", ATTR{idVendor}=="2717", MODE="0660", OWNER="node1"   # Xiaomi adb/MTP
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0660", OWNER="node1"   # fastboot
SUBSYSTEM=="usb", ATTR{idVendor}=="05c6", MODE="0660", OWNER="node1"   # Qualcomm EDL
RULES
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=usb
```

VID устройства: `2717:ff48` в режиме MTP+ADB, `18d1:d00d` в fastboot. ✅ ПРОВЕРЕНО

### SELinux

Если pmbootstrap падает с ошибками доступа/монтирования и `ausearch -m avc -ts recent`
показывает денайлы — временно `sudo setenforce 0` (вернуть `1` после работ, зафиксировать
в отчёте). **На этом сервере не потребовалось.**

## Фаза 2 — Установка pmbootstrap

⚠️ **НЕ ставить с PyPI.** `pip install pmbootstrap` даёт мёртвую версию **2.1.0** —
на PyPI пакет давно не обновляется. Ставить только из git.

⚠️ **Версию тега выбирать сортировкой по версиям, а не лексической.** `sort -V`, не `sort`:
лексически `3.10.0 < 3.9.0`, и можно легко взять устаревший тег.

```bash
# посмотреть реальный список версий
git ls-remote --tags https://gitlab.postmarketos.org/postmarketOS/pmbootstrap.git \
  | grep -v '\^{}' | sed 's|.*refs/tags/||' | sort -V | tail -8

# поставить (подставить актуальный тег; на 2026-08-17 это 3.11.1)
python3.11 -m pip install --user \
    "git+https://gitlab.postmarketos.org/postmarketOS/pmbootstrap.git@3.11.1"
~/.local/bin/pmbootstrap --version
```

**Требование к версии диктует не pmbootstrap, а pmaports.** В
`pmaports/pmaports.cfg` есть `pmbootstrap_min_version`; на текущем edge это **3.11.0**.
Если версия ниже — `pmbootstrap init` падает с `RuntimeError: Please update your
pmbootstrap version` уже ПОСЛЕ клонирования pmaports. Требование самого pmbootstrap 3.11 —
Python ≥ 3.10 (`requires-python` в его `pyproject.toml`).

## Фаза 3 — Конфигурация (`pmbootstrap init`)

`pmbootstrap init` полностью интерактивен, CLI-флагов для ответов нет (кроме
`--shallow-initial-clone`). Ответы подаются на stdin в строгом порядке.

Порядок вопросов (pmbootstrap 3.11.1) и наши ответы:

| # | Вопрос | Ответ |
|---|---|---|
| 1 | Work path | *(пусто = по умолчанию)* |
| 2 | pmaports path | *(пусто)* |
| 3 | Channel | `edge` |
| 4 | Vendor | `xiaomi` |
| 5 | Device codename | `vayu` |
| 6 | Kernel | **`huaxing`** ← критично |
| 7 | Username | `poco` |
| 8 | Audio backend | *(пусто = pulseaudio)* |
| 9 | WiFi backend | *(пусто = wpa_supplicant)* |
| 10 | usb-moded profile | *(пусто = developer)* |
| 11 | User interface | `phosh` |
| 12 | Service manager | *(пусто = systemd, дефолт для phosh)* |
| 13 | Change additional options? | `n` |
| 14 | Extra packages | `none` |
| 15 | Use host timezone? | `y` |
| 16 | Locale | `ru_RU.UTF-8` |
| 17 | Device hostname | *(пусто)* |
| 18 | Copy SSH keys? | `y` |
| 19 | Build outdated packages? | `y` |
| 20 | Zap existing chroots? | `y` |

```bash
printf '%s\n' "" "" "edge" "xiaomi" "vayu" "huaxing" "poco" "" "" "" "phosh" "" \
  "n" "none" "y" "" "" "y" "y" "y" | pmbootstrap init
```

**SSH-ключ.** Перед init создать ключ на сервере (`ssh-keygen -t ed25519 -N '' -f
~/.ssh/id_ed25519`), тогда появится вопрос №18 и ключ уедет в образ. Это даёт доступ на
телефон по SSH через USB-сеть после первой загрузки — без него проверки Фазы 6 придётся
набирать на экранной клавиатуре телефона.

**Обязательная верификация после init** (порядок вопросов может измениться в новой версии,
поэтому вслепую доверять нельзя):

```bash
pmbootstrap status
# ожидается:
#   Channel: systemd-edge (pmaports: main)
#   Device:  xiaomi-vayu (aarch64, kernel: huaxing)
#   UI:      phosh
#   systemd: yes
```

Отдельные значения меняются без повторного init: `pmbootstrap config locale ru_RU.UTF-8`.

## Фаза 3.5 — ⚠️ СБОРКА ЯДРА ВРУЧНУЮ (обязательно для vayu)

**Штатный пакет ядра для vayu не годится, образ с ним не соберётся и не загрузится.**

Суть проблемы: `device-xiaomi-vayu` требует `qcom/sm8150-xiaomi-vayu-huaxing.dtb`, а пакет
`linux-postmarketos-qcom-sm8150` (6.17.0) собирается из тарбола `gitlab.com/sm8150-mainline/linux`,
где vayu нет **ни в одном теге и ни в одной ветке**. Поддержка устройства живёт только в
`gitlab.postmarketos.org/soc/qualcomm-sm8150/linux`, ветка **`sm8150/7.0-wip`** (MR !17
«Reintroduce Xiaomi POCO X3 Pro (vayu)», смержен 2026-06-27, коммит `8e126dbc`).
Аналогичный MR в стабильную `sm8150/6.18` был закрыт.

Симптом без этой правки: `pmbootstrap install` падает на `mkinitfs` → `boot-deploy` →
`ERROR: Unable to find qcom/sm8150-xiaomi-vayu-huaxing.dtb`.

### Правка APKBUILD

В `device/testing/linux-postmarketos-qcom-sm8150/APKBUILD`:

```sh
pkgver=7.0.0
pkgrel=1
url="https://gitlab.postmarketos.org/soc/qualcomm-sm8150/linux"
_commit="8e126dbc4044ef2cec3ebe5754ddb05faa554af6"
source="
	linux-$_commit.tar.gz::$url/-/archive/$_commit/linux-$_commit.tar.gz
	config-$_flavor.$arch
"
builddir="$srcdir/linux-$_commit"
```

Патчи `0001-lid-switch-fix`, `0002-enable-ufs`, `0003-fix-llvm-build` **удалить** — на этой
ветке они не нужны, сборка проходит без них.

### ⚠️ Конфиг ядра — критично

`prepare()` обязан подмешать **фрагмент из самого дерева ядра**. Ветка 7.0-wip вводит символы,
которых в конфиге pmaports (написанном под 6.17) физически нет, и `olddefconfig` молча
выставляет их в «выключено»:

| Символ | Что ломается без него |
|---|---|
| `CONFIG_DRM_PANEL_HUAXING_NT36672=m` | **нет драйвера панели → нет DRM-карты → чёрный экран** |
| `CONFIG_DRM_PANEL_TIANMA_NT36672=m` | то же для второго варианта панели |
| `CONFIG_TOUCHSCREEN_NT36672_SPI=y` | **не работает тачскрин** |

```sh
prepare() {
	default_prepare
	cp "$srcdir/config-$_flavor.$arch" .config
	# merge_config.sh здесь неприменим: он требует GNU readlink -m,
	# а в Alpine-chroot стоит busybox. Дописываем фрагмент вручную,
	# конфликты разрешает olddefconfig (побеждает последнее значение).
	sed "s/[[:space:]]*#.*$//" arch/arm64/configs/sm8150.config \
		| grep "^CONFIG_" >> .config
	make ARCH="$_carch" LLVM=1 olddefconfig
}
```

**Диагностическая подсказка.** Драйвер drm/msm собирается через component framework и молча
ждёт все свои части. Если драйвера панели нет, узел `dsi@ae94000` не завершает регистрацию,
мастер не привязывается, DRM-карта не создаётся — и **в логе нет ни одной ошибки**, а
`/sys/kernel/debug/devices_deferred` пуст. Не ищите сообщение об ошибке, её не будет.
Признак: `/sys/class/drm/` содержит только `version`, но при этом есть `fb0` типа `simple`
(это фреймбуфер, оставленный загрузчиком) и включённая подсветка — экран «горит чёрным».

### Сборка

```sh
pmbootstrap checksum linux-postmarketos-qcom-sm8150   # качает ~250 МБ, запускать в фоне
pmbootstrap build linux-postmarketos-qcom-sm8150 --force
```

Время: **~45 мин** на холодную, **~10 мин** при прогретом ccache (16 потоков, cross-native,
без эмуляции). Проверка результата:

```sh
tar tzf ~/.local/var/pmbootstrap/packages/edge/aarch64/linux-*-7.0.0-r1.apk \
  | grep -E "panel-huaxing|vayu.*dtb"
# ожидается: panel-huaxing-nt36672.ko и оба sm8150-xiaomi-vayu-*.dtb
```

Если `pmbootstrap build` падает на `Zapping buildroots` с `umount ... exit code 32` —
остались висящие монтирования, лечится `pmbootstrap shutdown`.

## Фаза 4 — Сборка образа

Для первой попытки — **без полного шифрования диска (FDE)**, чтобы уменьшить число точек
отказа и быстрее проверить, что железо заводится. (FDE — отдельная итерация после успешной
первой загрузки, `pmbootstrap install --fde`, согласовать с оператором.)

`pmbootstrap install` спрашивает пароль пользователя дважды. Передавать через stdin из
файла, а не флагом `--password` (он светится в `ps`):

```bash
umask 077
printf 'ПАРОЛЬ\nПАРОЛЬ\n' > ~/.pmb_pw
setsid nohup bash -c 'pmbootstrap install < ~/.pmb_pw > ~/pmb-install.log 2>&1; \
    echo "EXITCODE=$?" >> ~/pmb-install.log; rm -f ~/.pmb_pw' >/dev/null 2>&1 &
```

Сборка идёт десятками минут (rootfs aarch64 собирается через эмуляцию), поэтому запускать
через `setsid nohup` — чтобы она пережила обрыв SSH-сессии.

### Известные сбои

- **`ERROR: <пакет>: Operation timed out`** на одном из пакетов при `install
  postmarketos-base-systemd` — это таймаут скачивания с зеркала, а не проблема эмуляции или
  SELinux. Лечится повтором: `pmbootstrap install --zap`.
- Детальный лог — `~/.local/var/pmbootstrap/log.txt` (в нём же вывод упавшей команды, над
  строкой `^^^^^`). Сообщения `Error relocating /usr/bin/udevadm: symbol not found` в
  процессе установки — шум, не причина сбоя.

## Фаза 5 — ЧЕЛОВЕЧЕСКИЙ ГЕЙТ: прошивка

**СТОП. Дальше без явного подтверждения человека не продолжать.**

Телефон переводится в fastboot командой, кнопки жать не нужно:

```bash
adb reboot bootloader
fastboot devices
fastboot getvar unlocked   # ожидается: unlocked: yes
```

- Если устройство не видно — проверить кабель/порт/режим и udev-правила из Фазы 1.
- Если `unlocked` не `yes` — НЕ прошивать, вернуть оператору. Напоминание: свойства
  Android на этот вопрос отвечать не могут (раздел 0).

При `unlocked: yes` и явном «go» от оператора — прошить:

```bash
pmbootstrap flasher flash_vbmeta    # ⚠️ ОБЯЗАТЕЛЬНО, СНАЧАЛА (см. ниже)
pmbootstrap flasher flash_kernel
pmbootstrap flasher flash_rootfs
```

### ⚠️ `flash_vbmeta` обязателен

Без него устройство **не загрузится**: покажет заставку POCO и уйдёт обратно в fastboot.
Причина — AVB: загрузчик отвергает неподписанный `boot`. `flash_vbmeta` пишет образ AVB 2.0
с флагом отключения проверки.

В `deviceinfo` для vayu имя раздела **не указано**, из-за чего команда падает с
`Your device does not have 'vbmeta' partition specified`. Добавить строку:

```
deviceinfo_flash_fastboot_partition_vbmeta="vbmeta"
```

**Не нужно** стирать `dtbo` — проверено, на загрузку не влияет.

Примечание: в старых версиях pmbootstrap `flash_rootfs` называется `flash_system`.
Свериться с `pmbootstrap flasher --help`.

Запись `userdata` (3 ГБ) идёт ~80 секунд тремя sparse-кусками. Строка
`Invalid sparse file format at header magic` — не ошибка, а сообщение о том, что fastboot
сам режет несжатый файл на части.

После прошивки — `fastboot reboot`.

### Как попасть в fastboot

- Из Android: `adb reboot bootloader`.
- Из postmarketOS: **кнопками**. `sudo reboot bootloader` и `systemctl reboot bootloader`
  НЕ работают — система останавливается, но загрузчику команда не передаётся, и телефон
  зависает. Восстановление: удержание Power 10–15 с, затем Vol Down + Power.

## Фаза 6 — Первая загрузка и проверка

- **Первая загрузка занимает до 8 минут.** Это измеренный факт, а не оценка. Не делать
  вывод «не загрузилось» раньше чем через 10 минут — легко принять живую систему за мёртвую.
- Ожидается Phosh. После загрузки экран может быть **погашен (suspend)** — нажать кнопку
  питания, появится ввод пароля. Клавиатура цифровая, поэтому временный пароль удобно
  делать числовым, а после входа менять через `passwd`.

### Доступ по SSH через USB-сеть

Ключ сервера уехал в образ на Фазе 3, профиль usb-moded `developer` включён по умолчанию.

```bash
# ⚠️ имя интерфейса непредсказуемо: systemd переименовывает usb0 во что-то
# вида enp4s0f4u1. Искать по исключению, а не по шаблону "usb*"!
IF=$(ls /sys/class/net/ | grep -vE '^(lo|docker0|br-|veth|<штатные NIC>)' | head -1)
sudo ip link set $IF up
sudo ip addr add 172.16.42.2/24 dev $IF     # dhclient в OL9 не установлен
ssh -i ~/.ssh/id_ed25519 poco@172.16.42.1
```

При каждой перепрошивке rootfs у телефона меняется ключ хоста — `ssh-keygen -R 172.16.42.1`.

### Признаки, по которым видно состояние устройства

| USB ID | Что это |
|---|---|
| `2717:ff48` | Android, режим MTP+ADB |
| `18d1:d00d` | fastboot |
| `18d1:d001`, `SerialNumber: postmarketOS`, `bcdDevice 7.00` | **pmOS загружен**, CDC-сетевой гаджет поднят |

### Проверка железа (выполнено, всё подтверждено на живом устройстве)

```bash
ls /sys/class/drm/                 # должны быть card0, card0-DSI-1
cat /sys/class/drm/card0-DSI-1/status         # connected
lsmod | grep panel                 # panel_huaxing_nt36672
grep '^N: Name' /proc/bus/input/devices       # NVTCapacitiveTouchScreen
loginctl show-session <id> -p Type            # wayland
nmcli -t -f DEVICE,TYPE,STATE dev             # wlan0
```

Результат на 2026-08-17: дисплей 1080×2400, тачскрин, GPU Adreno 640
(`adreno 2c00000.gpu: loaded qcom/a630_sqe.fw`), батарея, Wi-Fi-адаптер, разъём наушников,
USB-сеть, Phosh на Wayland — работают. Единственная упавшая служба — `qbootctl.service`
(управление A/B-слотами), для не-A/B устройства это норма.

### Проверка контроля трафика (ради чего всё затевалось)

`nftables` уже установлен и включён в образе (`sysinit.target.wants/nftables.service`),
доставать `apk add` не требуется. Правила из коробки:

```bash
sudo nft list ruleset
# chain input { policy drop;  ... iifname "wwan*" drop;  iifname "qmapmux*" drop }
sudo tcpdump -i any -n
```

Входящая цепочка по умолчанию `drop`, трафик на модемных интерфейсах режется.

**Замечание про вывод pmbootstrap.** Строка `Firewall is enabled, but will not work
(no support in kernel config for nftables)` в конце `pmbootstrap install` — **ложная**.
Функция, которая её печатает, только логирует и ничего не настраивает. Реальность
проверяется иначе: наличием модулей `nft_*` в пакете ядра и `nft list ruleset` на устройстве.

---

## 7. Что было исправлено в этой ревизии

Ошибки исходного ТЗ, выявленные на практике:

1. **«Хост — RHCK, не UEK»** — на деле ядро UEK. Ни на что не повлияло, но факт был неверен.
2. **«pmbootstrap ставится из pip/pipx»** — на PyPI лежит мёртвая 2.1.0; нужен git и
   Python ≥ 3.10, тогда как в системе был 3.9.
3. **Риск SELinux и binfmt/qemu был переоценён** — оба не проявились; зато недооценён
   реальный блокер: `sudo` без NOPASSWD.
4. **Не был учтён `qemu-user-static`, отсутствующий в репах OL9** — оказалось, он и не нужен.
5. **Не были упомянуты udev-правила** — без них adb/fastboot не работают от обычного пользователя.
6. **Не было предупреждения о подделке свойств загрузчика на xiaomi.eu** — самая опасная
   ловушка документа: по `getprop` устройство выглядит как заблокированный сток, и по этому
   признаку можно ошибочно уйти в Mi Unlock с неделей ожидания и поиском Windows-машины.

## 8. Бэкап (выполнено до прошивки)

- Основное пространство (`/sdcard`, user 0): **497 МБ, 217 файлов** →
  `/home/node1/vayu-backup/sdcard-user0/` на сервере (`adb pull -a`).
- Второе пространство (user 10): файлов нет, копировать нечего.
- **Что НЕ спасается без root:** `/data/data` и `/data/user/10` — внутренние данные
  приложений (сессии, переписки, seed'ы 2FA). Хранилище второго пространства
  (`/storage/emulated/10`) недоступно для `adb shell` даже когда пространство активно и
  разблокировано — `Permission denied`. Экспорт таких данных — только руками из самих
  приложений, до прошивки.
- Приложения второго пространства на момент бэкапа: Hiddify, AdGuard VPN, Telegram,
  GetContact, Opera. Оператор осознанно отказался от переноса их данных.

---

## Приложение — сводка для быстрого доступа

| Параметр | Значение |
|---|---|
| Устройство | Xiaomi POCO X3 Pro (M2102J20SG) |
| Codename | `vayu` (`vayu_global`) |
| SoC | sm8150 / Snapdragon 860 |
| Панель | **Huaxing NT36672C** → ядро `huaxing` |
| Загрузчик | разблокирован ✅ (`fastboot getvar unlocked` = `yes`) |
| Текущая ОС | xiaomi.eu MIUI 14.0.3, Android 13, без root |
| UI | Phosh + systemd, локаль `ru_RU.UTF-8`, юзер `poco` |
| Хост сборки | Oracle Linux 9.4, ядро UEK, x86_64 |
| Инструмент | pmbootstrap 3.11.1 из git, под python3.11 |

Порядок команд (после валидации и установки зависимостей):
```
pmbootstrap init      # xiaomi / vayu / huaxing / phosh / poco
pmbootstrap status    # ОБЯЗАТЕЛЬНО сверить device/kernel/ui
# --- Фаза 3.5: правка APKBUILD ядра на ветку sm8150/7.0-wip + фрагмент sm8150.config ---
pmbootstrap checksum linux-postmarketos-qcom-sm8150
pmbootstrap build linux-postmarketos-qcom-sm8150 --force
pmbootstrap install   # первая попытка без --fde
# --- человеческий гейт: подтверждение оператора ---
adb reboot bootloader
fastboot getvar unlocked
pmbootstrap flasher flash_vbmeta    # без него не загрузится
pmbootstrap flasher flash_kernel
pmbootstrap flasher flash_rootfs
fastboot reboot                     # первая загрузка до 8 минут
```

## 9. Статус: выполнено 2026-08-17

postmarketOS edge (Phosh, systemd, ядро `7.0.0-sm8150`) установлен и работает.
Экран, тачскрин, GPU, батарея, Wi-Fi-адаптер, USB-сеть, SSH по ключу и nftables — подтверждены
на живом устройстве. Панель Huaxing подтверждена независимо: загрузчик передаёт в cmdline
`msm_drm.dsi_display0=dsi_j20s_42_02_0b_video_display`, что по таблице вики соответствует
именно ей (Tianma была бы `dsi_j20s_36_02_0a_video_display`). Это самый надёжный способ
определить панель — он не требует root и работает уже из-под pmOS.

Не проверено: сотовая связь (звонки, SMS, мобильные данные), камера, GPS. В описании MR !17
они не заявлены как работающие.
