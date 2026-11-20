// LELE CUBE numeric reader. Common decimal -> binary64 -> binary32, matching NumPy.
// Integers with at most 15 significant digits and powers of ten through 10^22
// are exact binary64 operands. The single multiplication/division rounds once.
// Other spellings/ranges return control to the general validated reader.
#if defined(_MSC_VER)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
static bool whitespace(char c) { return c == ' ' || (c >= '\t' && c <= '\r'); }
static bool digit(char c) { return c >= '0' && c <= '9'; }
static bool decimal(const char*& p, const char* end, const double* powers, double& result) {
    bool negative = *p == '-';
    if (negative || *p == '+') ++p;
    long long mantissa = 0;
    int significant = 0, fractional = 0;
    bool any = false, dot = false;
    while (p < end) {
        if (digit(*p)) {
            any = true;
            if (mantissa || *p != '0') ++significant;
            if (significant > 15) return false;
            mantissa = mantissa * 10 + (*p - '0');
            fractional += dot;
        } else if (*p == '.' && !dot) dot = true;
        else break;
        ++p;
    }
    if (!any) return false;
    int exponent = 0;
    if (p < end && (*p == 'E' || *p == 'e' || *p == 'D' || *p == 'd')) {
        ++p;
        bool neg_exp = p < end && *p == '-';
        if (p < end && (neg_exp || *p == '+')) ++p;
        if (p == end || !digit(*p)) return false;
        while (p < end && digit(*p)) {
            if (exponent > 10000) return false;
            exponent = exponent * 10 + (*p++ - '0');
        }
        if (neg_exp) exponent = -exponent;
    }
    if (p < end && !whitespace(*p)) return false;
    exponent -= fractional;
    if (exponent < -22 || exponent > 22) return false;
    double v = static_cast<double>(mantissa);
    v = exponent < 0 ? v / powers[-exponent] : v * powers[exponent];
    result = negative ? -v : v;
    return true;
}

extern "C" EXPORT int lele_cube_numbers(const char* p, int size, float* out, int capacity, const double* powers) {
    const char* end = p + size;
    int written = 0;
    while (p < end) {
        while (p < end && whitespace(*p)) ++p;
        if (p == end) break;
        double value;
        if (written == capacity || !decimal(p, end, powers, value)) return -1;
        out[written++] = static_cast<float>(value);
    }
    return written;
}

static void horizontal(const char*& p, const char* end) {
    while (p < end && *p != '\n' && whitespace(*p)) ++p;
}

// Standard XDATCAR / XYZ rows only. Any extension or uncommon number goes
// through the existing format reader. Symbols use their full ASCII spelling.
extern "C" EXPORT int lele_coordinate_rows(const char* p, int size, double* out, int rows,
                                          unsigned short* symbols, const double* powers) {
    const char* end = p + size;
    for (int row = 0; row < rows; ++row) {
        horizontal(p, end);
        if (symbols) {
            if (p == end || *p < 'A' || *p > 'Z') return 0;
            unsigned short symbol = static_cast<unsigned short>(*p++) << 8;
            if (p < end && *p >= 'a' && *p <= 'z') symbol |= *p++;
            if (p == end || !whitespace(*p)) return 0;
            symbols[row] = symbol;
        }
        for (int col = 0; col < 3; ++col) {
            horizontal(p, end);
            if (p == end || !decimal(p, end, powers, *out++)) return 0;
        }
        horizontal(p, end);
        if (p < end && *p != '\n') return 0;
        if (p < end) ++p;
    }
    return p == end;
}
