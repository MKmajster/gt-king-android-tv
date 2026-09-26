/*
 * btdiag - Bluetooth diagnostics for galilei v2 (no hciconfig/btmgmt/btmon on Android).
 *   btdiag       hci0 flags/address (HCIGETDEVINFO) + mgmt index lists (configured, unconfigured)
 *   btdiag up    HCIDEVUP on hci0 while capturing the monitor channel: every HCI command and the
 *                status it got (finds the command that makes the kernel's __hci_init fail)
 * Freestanding like btuart-attach.c (raw aarch64 syscalls, no libc).
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

static long sc(long n, long a, long b, long c, long d)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	register long x3 __asm__("x3") = d;
	__asm__ volatile("svc 0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3) : "memory", "cc");
	return x0;
}

static long sc5(long n, long a, long b, long c, long d, long e)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	register long x3 __asm__("x3") = d;
	register long x4 __asm__("x4") = e;
	__asm__ volatile("svc 0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4) : "memory", "cc");
	return x0;
}

#define NL "\n"
static void out(const char *s, long n) { sc(64, 1, (long)s, n, 0); }
static void say(const char *s) { long n = 0; while (s[n]) n++; out(s, n); }
static void hex(unsigned long v, int digits)
{
	char b[16];
	for (int i = digits - 1; i >= 0; i--, v >>= 4)
		b[i] = "0123456789abcdef"[v & 15];
	out(b, digits);
}

struct hci_dev_info {
	u16 dev_id;
	char name[8];
	u8 bdaddr[6];
	u32 flags;
	u8 type;
	u8 features[8];
	u32 pkt_type, link_policy, link_mode;
	u16 acl_mtu, acl_pkts, sco_mtu, sco_pkts;
	u32 stat[10];
} __attribute__((packed));

struct sockaddr_hci { u16 family, dev, channel; };

static void mgmt(int fd, u16 op, const char *what)
{
	u8 buf[64];
	u16 *h = (u16 *)buf;
	h[0] = op; h[1] = 0xffff; h[2] = 0;
	sc(64, fd, (long)buf, 6, 0);
	for (int tries = 0; tries < 8; tries++) {
		long n = sc(63, fd, (long)buf, sizeof(buf), 0);
		if (n < 6)
			break;
		/* Command Complete event 0x0001: opcode(2) status(1) num(2) index[] */
		if (h[0] == 1 && buf[6] == (op & 0xff)) {
			say(what); say(": status "); hex(buf[8], 2);
			say(" count "); hex(buf[9], 2); say(" idx");
			for (int i = 0; i < buf[9] && i < 8; i++) { say(" "); hex(buf[11 + 2 * i], 2); }
			say(NL);
			return;
		}
	}
	say(what); say(": no reply" NL);
}

static void info(void)
{
	struct hci_dev_info di;
	struct sockaddr_hci a = { 31, 0xffff, 3 };   /* AF_BLUETOOTH, HCI_DEV_NONE, HCI_CHANNEL_CONTROL */
	int fd = sc(198, 31, 3, 1, 0);                /* socket(AF_BLUETOOTH, SOCK_RAW, BTPROTO_HCI) */
	struct { long s, us; } tv = { 2, 0 };

	if (fd < 0) { say("socket failed" NL); return; }
	di.dev_id = 0;
	if (sc(29, fd, 0x800448d3, (long)&di, 0) == 0) {  /* HCIGETDEVINFO */
		say("hci0 flags 0x"); hex(di.flags, 8);
		say(" (UP=1 INIT=2 RUNNING=4 PSCAN=8 ISCAN=16 AUTH=32 ENCRYPT=64 INQUIRY=128 RAW=256)" NL);
		say("hci0 bdaddr ");
		for (int i = 5; i >= 0; i--) { hex(di.bdaddr[i], 2); if (i) say(":"); }
		say(" type "); hex(di.type, 2); say(NL);
	} else {
		say("HCIGETDEVINFO failed" NL);
	}
	sc(57, fd, 0, 0, 0);
	fd = sc(198, 31, 3, 1, 0);
	if (sc(200, fd, (long)&a, sizeof(a), 0) < 0) { say("bind mgmt failed" NL); return; }
	sc5(208, fd, 1, 20, (long)&tv, sizeof(tv));   /* SO_RCVTIMEO 2 s */
	mgmt(fd, 0x0003, "READ_INDEX_LIST");
	mgmt(fd, 0x0036, "READ_UNCONF_INDEX_LIST");
}

static void up(void)
{
	struct sockaddr_hci m = { 31, 0xffff, 2 };   /* HCI_CHANNEL_MONITOR */
	static u8 buf[1100];
	int mon = sc(198, 31, 3 | 04000, 1, 0);      /* SOCK_RAW | SOCK_NONBLOCK */
	int fd = sc(198, 31, 3, 1, 0);
	long r;

	if (sc(200, mon, (long)&m, sizeof(m), 0) < 0) { say("bind monitor failed" NL); return; }
	r = sc(29, fd, 0x400448c9, 0, 0);            /* HCIDEVUP hci0 (synchronous) */
	say("HCIDEVUP -> ");
	if (r < 0) { say("-"); hex(-r, 4); } else hex(r, 4);
	say(NL);
	for (int i = 0; i < 400; i++) {
		long n = sc(63, mon, (long)buf, sizeof(buf), 0);
		if (n < 6)
			break;
		u16 op = buf[0] | buf[1] << 8;
		u8 *d = buf + 6;
		if (op == 2) {                            /* command sent */
			say("cmd "); hex(d[0] | d[1] << 8, 4); say(NL);
		} else if (op == 3 && d[0] == 0x0e) {     /* command complete */
			say("  cc  "); hex(d[3] | d[4] << 8, 4); say(" status "); hex(d[5], 2); say(NL);
		} else if (op == 3 && d[0] == 0x0f) {     /* command status */
			say("  cs  "); hex(d[4] | d[5] << 8, 4); say(" status "); hex(d[2], 2); say(NL);
		} else if (op != 4 && op != 5 && op != 6 && op != 7) {
			say("mon "); hex(op, 2); say(NL);     /* index new/del, open/close, notes */
		}
	}
}

/* "mon": print the monitor channel for 30 s (start before btuart-attach to see the first init) */
static void mon(void)
{
	struct sockaddr_hci m = { 31, 0xffff, 2 };
	static u8 buf[1100];
	struct { long s, us; } tv = { 1, 0 };
	int fd = sc(198, 31, 3, 1, 0);

	if (sc(200, fd, (long)&m, sizeof(m), 0) < 0) { say("bind monitor failed" NL); return; }
	sc5(208, fd, 1, 20, (long)&tv, sizeof(tv));
	for (int t = 0; t < 30; ) {
		long n = sc(63, fd, (long)buf, sizeof(buf), 0);
		if (n < 6) { t++; continue; }
		u16 op = buf[0] | buf[1] << 8;
		u8 *d = buf + 6;
		if (op == 2) {
			say("cmd "); hex(d[0] | d[1] << 8, 4); say(" len "); hex(d[2], 2); say(NL);
		} else if (op == 3 && d[0] == 0x0e) {
			say("  cc  "); hex(d[3] | d[4] << 8, 4); say(" status "); hex(d[5], 2); say(NL);
		} else if (op == 3 && d[0] == 0x0f) {
			say("  cs  "); hex(d[4] | d[5] << 8, 4); say(" status "); hex(d[2], 2); say(NL);
		} else if (op == 3) {
			say("  evt "); hex(d[0], 2); say(NL);
		} else if (op != 4 && op != 5 && op != 6 && op != 7) {
			say("mon "); hex(op, 2); say(NL);
		}
	}
}

void __attribute__((noreturn)) cmain(long argc, char **argv)
{
	if (argc > 1 && argv[1][0] == 'm')
		mon();
	if (argc > 1 && argv[1][0] == 'u')
		up();
	info();
	sc(93, 0, 0, 0, 0);
	__builtin_unreachable();
}

__asm__(".globl _start\n_start:\n  ldr x0, [sp]\n  add x1, sp, #8\n  bl cmain\n");
