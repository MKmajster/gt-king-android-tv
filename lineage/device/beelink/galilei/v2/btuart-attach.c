/*
 * btuart-attach - attach the AP6275S Bluetooth UART (/dev/ttyS1, UART_A) to the kernel HCI UART
 * line discipline with the Broadcom protocol, then stay alive holding the tty (galilei v2).
 *
 * voodik's ODROID-N2 vendor only knows USB Bluetooth dongles: its HAL
 * (android.hardware.bluetooth@1.1-service.btlinux) talks to an existing hci0 over an HCI user
 * channel. On the GT-King the controller sits on a UART, so something has to create hci0 - the job
 * of btattach/hciattach on a desktop, which Android does not ship. The kernel (CONFIG_BT_HCIUART_BCM)
 * then downloads the patch itself (btbcm_initialize -> request_firmware("brcm/<chip>.hcd"), served
 * by ueventd from /vendor/firmware/brcm/) and switches to the protocol's operating speed.
 *
 * Freestanding (no libc: this tree has no NDK sysroot), raw aarch64 syscalls:
 *   clang --target=aarch64-linux-gnu -O2 -ffreestanding -fno-stack-protector -nostdlib -static \
 *         -fuse-ld=lld -o btuart-attach btuart-attach.c
 * Usage: btuart-attach [tty]   (default /dev/ttyS1)
 */
typedef unsigned int u32;
typedef unsigned char u8;

#define AT_FDCWD (-100)
#define O_RDWR 02
#define O_NOCTTY 0400
#define TCGETS 0x5401
#define TCSETS 0x5402
#define TCFLSH 0x540B
#define TIOCSETD 0x5423
#define HCIUARTSETPROTO 0x400455c8 /* _IOW('U', 200, int) */
#define N_HCI 15
#define HCI_UART_BCM 7

struct termios {           /* asm-generic, NCCS = 19 */
	u32 c_iflag, c_oflag, c_cflag, c_lflag;
	u8 c_line;
	u8 c_cc[19];
};

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

static void say(const char *s)
{
	long n = 0;
	while (s[n])
		n++;
	sc(64, 2, (long)s, n, 0);  /* write(2, ...) */
}

static void die(const char *s)
{
	say("btuart-attach: ");
	say(s);
	say("\n");
	sc(93, 1, 0, 0, 0);        /* exit(1) */
}

void __attribute__((noreturn)) cmain(long argc, char **argv)
{
	const char *tty = argc > 1 ? argv[1] : "/dev/ttyS1";
	struct termios t;
	int ld = N_HCI, proto = HCI_UART_BCM;
	long fd = sc(56, AT_FDCWD, (long)tty, O_RDWR | O_NOCTTY, 0);   /* openat */

	if (fd < 0)
		die("open tty failed");
	if (sc(29, fd, TCGETS, (long)&t, 0) < 0)
		die("TCGETS failed");
	t.c_iflag = 0;
	t.c_oflag = 0;
	t.c_lflag = 0;
	/* B115200 | CS8 | CREAD | CLOCAL | CRTSCTS: the BCM ROM boots at 115200 with flow control */
	t.c_cflag = 0010002 | 0000060 | 0000200 | 0004000 | 020000000000;
	t.c_cc[5] = 0;             /* VTIME */
	t.c_cc[6] = 1;             /* VMIN */
	if (sc(29, fd, TCSETS, (long)&t, 0) < 0)
		die("TCSETS failed");
	sc(29, fd, TCFLSH, 2, 0);  /* TCIOFLUSH */
	if (sc(29, fd, TIOCSETD, (long)&ld, 0) < 0)
		die("TIOCSETD N_HCI failed");
	if (sc(29, fd, HCIUARTSETPROTO, proto, 0) < 0)
		die("HCIUARTSETPROTO bcm failed");
	say("btuart-attach: hci attached (bcm)\n");
	for (;;)
		sc(73, 0, 0, 0, 0);    /* ppoll(NULL, 0, NULL, NULL): sleep until killed */
}

__asm__(
	".globl _start\n"
	"_start:\n"
	"  ldr x0, [sp]\n"         /* argc */
	"  add x1, sp, #8\n"       /* argv */
	"  bl cmain\n");
