class Main : Object {
  run [ |
    s := 'Hello' concatenateWith: ', World!'.
    _ := s print.
    len := s length.
    ls := len asString.
    _ := ls print.
  ]
}
