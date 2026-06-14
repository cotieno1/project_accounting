(function (global) {
    function currencySymbol() {
        return (global.APP_CURRENCY && global.APP_CURRENCY.symbol) || "US$";
    }

    function fmtMoney(amount, options) {
        const opts = options || {};
        const sym = opts.symbol != null ? opts.symbol : currencySymbol();
        const n = parseFloat(amount);
        if (Number.isNaN(n)) {
            return sym + " 0.00";
        }
        const formatted = n.toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return sym + " " + formatted;
    }

    global.fmtMoney = fmtMoney;
    global.currencySymbol = currencySymbol;
})(typeof window !== "undefined" ? window : globalThis);
