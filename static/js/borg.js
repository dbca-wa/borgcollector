function insert_datasource_fields(src) {
    var vrt = editor_source.getDoc().getValue();
    var foreign_table = $('#id_foreign_table').val();
    var name = $('#id_name').val();
    var btn_name = null;
    if (src != null) {
        btn_name = $(src).val()
        $(src).val("Processing...");
        $(src).attr('disabled','disabled')
    }
    function post_process() {
        if (src != null) {
            $(src).val(btn_name);
            $(src).removeAttr('disabled')
        }
    }
    $.ajax({
        url: "/vrtfile",
        type: "POST",
        data: {name:name, foreign_table:foreign_table,vrt:vrt,action:"insert_fields"},
        dataType: "text",
        xhrFields: {
            withCredentials: true
        },
        success: function(data,statusCode){
            editor_source.getDoc().setValue(data);
            post_process();
        },
        error: function(jqxhr,statusCode,error) {
            alert(statusCode + ":" + error);
            post_process();
        }

    });
}
